import hashlib
import json
import re
import shutil
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import sqrt, isfinite
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from simulation.orbit import MU, EARTH_RADIUS, orbital_status
from safety.emergency import assess
from guidance.recovery import plan_recovery
from safety.validator import validate_independently
from navigation.deadline import time_to_altitude
from singularos_sim.config import load_config, with_seed
from singularos_sim.replay import FrameBuilder, build_replay, replay_html
from singularos_sim.runner import DEFAULT_RUNS_DIR, run_scenario

SCENARIOS_DIR = Path(__file__).resolve().parents[1] / "scenarios"
LAUNCHER = Path(__file__).resolve().parent / "launcher.html"
REPLAY_TEMPLATE = Path(__file__).resolve().parents[1] / "singularos_sim" / "replay_template.html"
REPLAY_CODE = Path(__file__).resolve().parents[1] / "singularos_sim" / "replay.py"


def replay_stale(out):
    """True if the run's replay page is missing or older than the replay code."""
    page = out / "replay.html"
    newest = max(REPLAY_TEMPLATE.stat().st_mtime, REPLAY_CODE.stat().st_mtime)
    return not page.exists() or page.stat().st_mtime < newest
_copilot = None
TRACK_PERIOD_S = 1.0


def mission_snapshot(disturbance_m_s=150):
    radius = EARTH_RADIUS + 400
    position = (radius, 0, 0)
    velocity = (0, sqrt(MU / radius) - disturbance_m_s / 1000, 0)

    emergency = assess(position, velocity, communications=False)
    plan = plan_recovery(position, velocity)
    safety = validate_independently(position, velocity, plan)

    return {
        "mode": "SIMULATION",
        "disturbance_m_s": disturbance_m_s,
        "initial_orbit": orbital_status(position, velocity),
        "hazards": emergency["hazards"],
        "time_to_120km_seconds": time_to_altitude(position, velocity),
        "recovery_plan": plan,
        "safety_verification": safety,
        "recovery_feasible": safety["authorized"],
    }


def scenario_names():
    return sorted(p.stem for p in SCENARIOS_DIR.glob("*.toml"))


def list_scenarios():
    out = []
    for name in scenario_names():
        config = load_config(SCENARIOS_DIR / f"{name}.toml")
        out.append({"name": name, "expected_outcome": config["scenario"]["expected_outcome"],
                    "expected_outcome_copilot": config["scenario"]["expected_outcome_copilot"],
                    "faults": config["faults"],
                    "advisories": [{"id": a["id"], "text": a["text"]} for a in config["advisories"]],
                    "station": config["station"]["components"]})
    return out


def copilot_agent():
    """The LLM copilot (created once), or None if the model server is unavailable."""
    global _copilot
    if _copilot is None:
        from intelligence.copilot import CopilotAgent
        from intelligence.llm import LLMClient

        client = LLMClient()
        if client.health()["ok"]:
            _copilot = CopilotAgent(client)
    return _copilot


def copilot_status():
    from intelligence.llm import LLMClient

    client = LLMClient()
    status = client.health()
    return {"ok": status["ok"], "detail": status["detail"], "model": client.config.model}


def run_dir(name, seed, copilot=False):
    return DEFAULT_RUNS_DIR / f"{name}-{'copilot-' if copilot else ''}seed{seed}"


RUN_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def next_run_dir(name, seed, copilot):
    """A new numbered run directory: <base>-r1, -r2, ... (keeps every run)."""
    base = run_dir(name, seed, copilot).name
    taken = [int(m.group(1)) for p in DEFAULT_RUNS_DIR.glob(f"{base}-r*")
             if (m := re.fullmatch(re.escape(base) + r"-r(\d+)", p.name))]
    return DEFAULT_RUNS_DIR / f"{base}-r{max(taken, default=0) + 1}"


def ensure_run(name, seed, copilot=False, force=False, new=False):
    """Run the scenario unless a finished run for it already exists (or force).
    new: always run again into a new numbered directory."""
    config = with_seed(load_config(SCENARIOS_DIR / f"{name}.toml"), seed)
    out = next_run_dir(name, config["scenario"]["seed"], copilot) if new else run_dir(name, config["scenario"]["seed"], copilot)
    if new or force or not (out / "summary.json").exists():
        agent = copilot_agent() if copilot else None
        if copilot and agent is None:
            raise ValueError("AI copilot unavailable: start `ollama serve` and pull the model")
        run_scenario(config, out, copilot=agent)
        build_replay(out)
    elif replay_stale(out):
        build_replay(out)  # missing, or built from an older replay page
    return out


def _cached(out, filename, compute):
    path = out / filename
    log = out / "log.jsonl"
    if path.exists() and path.stat().st_mtime >= log.stat().st_mtime:
        return json.loads(path.read_text())
    value = compute()
    path.write_text(json.dumps(value))
    return value


def run_path(out):
    """Truth track sampled every TRACK_PERIOD_S, as [[t, x, y], ...]."""
    def compute():
        pts, next_t = [], 0.0
        with open(out / "log.jsonl") as f:
            for line in f:
                rec = json.loads(line)
                if rec["t"] + 1e-9 >= next_t:
                    tr = rec["truth"]
                    pts.append([round(rec["t"], 1), round(tr["x_m"], 2), round(tr["y_m"], 2)])
                    next_t += TRACK_PERIOD_S
        return pts
    return _cached(out, "path.json", compute)


def run_entry(out):
    """One history row for a finished run directory."""
    s = json.loads((out / "summary.json").read_text())
    digest = _cached(out, "digest.json", lambda: hashlib.sha256((out / "log.jsonl").read_bytes()).hexdigest()[:16])
    copilot = s.get("copilot", [])
    proposals = [e for e in copilot if e["type"] == "copilot_proposal"]
    verdicts = [e for e in copilot if e["type"] == "copilot_verdict"]
    accepted = next((p for p, v in zip(proposals, verdicts) if v["accepted"]), None)
    plan = s.get("plan") or {}
    passed = (s["outcome"] == s["expected_outcome"] and s["collision"] is None and not s.get("advisory_violations")
              and (s["outcome"] != "DOCKED" or s["truth_docking_check"]["pass"]))
    return {
        "run": out.name, "time": out.joinpath("summary.json").stat().st_mtime,
        "scenario": s["scenario"], "seed": s["seed"], "mode": s.get("mode", "baseline"), "model": s.get("copilot_model"),
        "outcome": s["outcome"], "expected": s["expected_outcome"], "pass": passed,
        "violations": [v["type"] for v in s.get("advisory_violations", [])], "collision": s["collision"] is not None,
        "sim_time_s": s["sim_time_s"], "fuel_used_kg": round(s["fuel_used_kg"], 3),
        "authority": s.get("authority", "baseline"),
        "proposals": [{"decision": p["plan"]["decision"], "steps": p["plan"]["steps"], "latency_s": p["latency_s"],
                       "accepted": v["accepted"], "problems": v["problems"]} for p, v in zip(proposals, verdicts)],
        "errors": [e["error"] for e in copilot if e["type"] == "copilot_error"],
        "final_plan": accepted["plan"]["steps"] if accepted else None,
        "final_decision": accepted["plan"]["decision"] if accepted else plan.get("decision"),
        "digest": digest,
    }


def history(name=None, seed=None, copilot=None):
    rows = []
    for out in DEFAULT_RUNS_DIR.glob("*"):
        if not (out / "summary.json").exists() or not (out / "log.jsonl").exists():
            continue
        try:
            row = run_entry(out)
        except (KeyError, ValueError, OSError):
            continue
        if name and row["scenario"] != name:
            continue
        if seed is not None and row["seed"] != seed:
            continue
        if copilot is not None and (row["mode"] == "copilot") != copilot:
            continue
        rows.append(row)
    return sorted(rows, key=lambda r: r["time"], reverse=True)


# ------------------------------------------------------------------ live mode
#
# A live session runs a scenario in a background thread, paced to a playback
# speed, and keeps the replay frames it produces so browsers can stream them
# (/api/live/stream). While the AI copilot is thinking the controller holds
# position and the simulation is paced at 1x, so the simulated wait equals the
# model's real latency. The finished run is saved like any other run; a
# cancelled run stops at its next step and its directory is removed.

LIVE = {}
LIVE_LOCK = threading.Lock()


class Cancelled(Exception):
    """Raised from the observer to stop a live run."""


class LiveSession:
    def __init__(self, name, seed, copilot, speed):
        self.id = uuid.uuid4().hex[:12]
        self.config = with_seed(load_config(SCENARIOS_DIR / f"{name}.toml"), seed)
        self.out = next_run_dir(name, self.config["scenario"]["seed"], copilot)
        self.copilot = copilot
        self.speed = speed
        self.frames = []
        self.builder = FrameBuilder()
        self.summary = None
        self.error = None
        self.done = False
        self.cancelled = False  # the run was stopped before it finished
        self._stop = False
        self.lock = threading.Lock()
        self._wall = None
        self._last_t = 0.0

    def provisional_summary(self):
        sc = self.config["scenario"]
        return {"scenario": sc["name"], "seed": sc["seed"], "mode": "copilot" if self.copilot else "baseline",
                "outcome": "RUNNING", "expected_outcome": sc["expected_outcome_copilot" if self.copilot else "expected_outcome"],
                "sim_time_s": 0.0, "fuel_used_kg": 0.0, "inspections_completed": [], "collision": None,
                "min_clearance_in_flight": {"clearance_m": None}, "truth_docking_check": {"pass": False},
                "advisory_violations": []}

    def cancel(self):
        self._stop = True

    def observe(self, record, controller):
        if self._stop:
            raise Cancelled
        frame = self.builder.feed(record)
        if frame is not None:
            with self.lock:
                self.frames.append(frame)
        # Pace simulated time against the wall clock.
        now = time.monotonic()
        if self._wall is None:
            self._wall = now
        dt = record["t"] - self._last_t
        self._last_t = record["t"]
        self._wall += dt / (1.0 if controller.pending is not None else self.speed)
        if self._wall - now > 0.005:
            time.sleep(self._wall - now)
        elif now - self._wall > 1.0:
            self._wall = now  # fell behind (e.g. slow machine): do not try to catch up

    def run(self):
        try:
            agent = copilot_agent() if self.copilot else None
            if self.copilot and agent is None:
                raise ValueError("AI copilot unavailable: start `ollama serve` and pull the model")
            summary = run_scenario(self.config, self.out, copilot=agent, observer=self.observe, copilot_async=self.copilot)
            build_replay(self.out)
            self.summary = {k: v for k, v in summary.items() if k != "out_dir"}
        except Cancelled:
            self.cancelled = True
            shutil.rmtree(self.out, ignore_errors=True)
        except Exception as e:  # reported to the browser
            self.error = f"{type(e).__name__}: {e}"
        finally:
            self.done = True


def start_live(name, seed, copilot, speed):
    session = LiveSession(name, seed, copilot, speed)
    with LIVE_LOCK:
        LIVE[session.id] = session
    threading.Thread(target=session.run, daemon=True).start()
    return session


def run_report(out):
    """Summary, a track sampled every TRACK_PERIOD_S, and controller events."""
    summary = json.loads((out / "summary.json").read_text())
    summary.pop("out_dir", None)
    track, events, next_t = [], [], 0.0
    with open(out / "log.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            ctrl = rec.get("controller")
            if ctrl is None:
                continue
            events += [{"t": rec["t"], **e} for e in ctrl.get("events", [])]
            if rec["t"] + 1e-9 >= next_t:
                tr = rec["truth"]
                track.append({"t": round(rec["t"], 2), "x_m": round(tr["x_m"], 2), "y_m": round(tr["y_m"], 2),
                              "phase": ctrl["phase"], "fuel_kg": round(tr["fuel_kg"], 4),
                              "altitude_km": tr["orbit"]["altitude_km"], "perigee_km": tr["orbit"]["perigee_km"]})
                next_t += TRACK_PERIOD_S
    return {"summary": summary, "track": track, "events": events}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data):
        payload = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def scenario_args(self, query):
        name = query.get("scenario", [""])[0]
        if name not in scenario_names():
            raise ValueError(f"Unknown scenario: {name!r}")
        raw = query.get("seed", [None])[0]
        seed = None if raw is None else int(raw)
        if seed is not None and not 0 <= seed <= 1_000_000:
            raise ValueError("Seed must be between 0 and 1000000")
        flag = lambda k: query.get(k, ["0"])[0] in ("1", "true", "yes")
        return name, seed, flag("copilot"), flag("force"), flag("new")

    def send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def stream(self, session):
        """Server-Sent Events: batches of new frames, then the final summary."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        sent = 0
        try:
            while True:
                with session.lock:
                    batch = session.frames[sent:]
                if batch:
                    sent += len(batch)
                    self.wfile.write(b"event: frames\ndata: " + json.dumps(batch, separators=(",", ":")).encode() + b"\n\n")
                    self.wfile.flush()
                elif session.done:
                    end = {"summary": session.summary, "error": session.error, "cancelled": session.cancelled,
                           "run": session.out.name}
                    self.wfile.write(b"event: end\ndata: " + json.dumps(end).encode() + b"\n\n")
                    self.wfile.flush()
                    return
                time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError):
            return  # browser closed the page; the run continues and is saved

    def run_by_id(self, query):
        run = query.get("run", [""])[0]
        out = DEFAULT_RUNS_DIR / run
        if not RUN_ID.match(run) or not (out / "summary.json").exists():
            raise ValueError(f"Unknown run: {run!r}")
        return out

    def do_GET(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            html = LAUNCHER.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        if url.path == "/api/scenarios":
            self.send_json(list_scenarios())
            return
        if url.path == "/api/copilot":
            self.send_json(copilot_status())
            return
        if url.path == "/api/live/start":
            try:
                name, seed, copilot, _, _ = self.scenario_args(query)
                speed = float(query.get("speed", ["20"])[0])
                if not 1 <= speed <= 200:
                    raise ValueError("speed must be between 1 and 200")
            except ValueError as error:
                self.send_error(400, str(error))
                return
            session = start_live(name, seed, copilot, speed)
            self.send_json({"id": session.id, "run": session.out.name})
            return
        if url.path in ("/api/live/view", "/api/live/stream", "/api/live/status", "/api/live/cancel"):
            session = LIVE.get(query.get("id", [""])[0])
            if session is None:
                self.send_error(404, "Unknown live session")
                return
            if url.path == "/api/live/cancel":
                session.cancel()
                self.send_json({"cancelled": True})
            elif url.path == "/api/live/status":
                self.send_json({"done": session.done, "error": session.error, "cancelled": session.cancelled,
                                "run": session.out.name,
                                "frames": len(session.frames), "summary": session.summary})
            elif url.path == "/api/live/view":
                self.send_html(replay_html(session.config, session.provisional_summary(), [], None,
                                           {"id": session.id, "speed": session.speed}, session.out.name).encode())
            else:
                self.stream(session)
            return
        if url.path == "/api/history":
            name = query.get("scenario", [None])[0]
            seed = query.get("seed", [None])[0]
            mode = query.get("copilot", [None])[0]
            self.send_json(history(name, None if seed is None else int(seed),
                                   None if mode is None else mode in ("1", "true", "yes")))
            return
        if url.path in ("/api/path", "/api/replay") and "run" in query:
            try:
                out = self.run_by_id(query)
            except ValueError as error:
                self.send_error(400, str(error))
                return
            if url.path == "/api/path":
                self.send_json(run_path(out))
            else:
                if replay_stale(out):
                    build_replay(out)
                self.send_html((out / "replay.html").read_bytes())
            return
        if url.path in ("/api/run", "/api/replay"):
            try:
                name, seed, copilot, force, new = self.scenario_args(query)
                is_run = url.path == "/api/run"
                out = ensure_run(name, seed, copilot, force and is_run, new and is_run)
            except ValueError as error:
                self.send_error(400, str(error))
                return
            if url.path == "/api/run":
                self.send_json({**run_report(out), "run": out.name})
                return
            html = (out / "replay.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        if url.path != "/api/mission":
            self.send_error(404)
            return

        try:
            raw = parse_qs(url.query).get("disturbance", ["150"])[0]
            disturbance = float(raw)
            if not isfinite(disturbance) or not 0 <= disturbance <= 300:
                raise ValueError("Disturbance must be between 0 and 300 m/s")
        except ValueError as error:
            self.send_error(400, str(error))
            return

        self.send_json(mission_snapshot(disturbance))


if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Scenario launcher: http://127.0.0.1:{port}  (API: /api/scenarios, /api/run, /api/replay)", flush=True)
    server.serve_forever()
