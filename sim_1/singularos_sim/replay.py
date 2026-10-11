"""Build a self-contained HTML replay of a finished run.

Reads config.json, summary.json and log.jsonl from a run directory and writes
replay.html next to them. The page has no external dependencies. It samples
one frame per controller tick and shows truth and observations as separate
layers.

Usage: python -m singularos_sim.replay <run_dir>
"""

import json
import sys
from pathlib import Path

from .config import THRUSTER_NAMES

TEMPLATE = Path(__file__).resolve().parent / "replay_template.html"


def _r(v, nd=4):
    return None if v is None else round(v, nd)


def build_frames(log_path):
    frames = []
    latest = {}
    last_seen = {}  # latest observation per source, available or not
    pending_events = []
    with open(log_path) as f:
        for line in f:
            rec = json.loads(line)
            pending_events += [{**e, "source": "truth"} for e in rec["truth"].get("events", [])]
            for obs in rec["observations"]:
                last_seen[obs["source"]] = obs
                if obs["available"]:
                    latest[obs["source"]] = obs
            ctrl = rec.get("controller")
            if ctrl is None:
                continue
            tr = rec["truth"]
            nav = latest.get("navigation")
            att = latest.get("attitude_sensor")
            fuel = latest.get("fuel_monitor")
            pending_events += [{**e, "source": "controller"} for e in ctrl.get("events", [])]
            dock = ctrl["docking_check"]
            frames.append({
                "t": _r(rec["t"], 3),
                "phase": ctrl["phase"],
                "leg": ctrl["leg"],
                "clear": _r(tr["station_clearance_m"], 3),
                "truth": [_r(tr["x_m"]), _r(tr["y_m"]), _r(tr["vx_m_s"]), _r(tr["vy_m_s"]),
                          _r(tr["heading_rad"]), _r(tr["angular_rate_rad_s"]), _r(tr["fuel_kg"])],
                "thrust": [_r(tr["thrust_n"][n], 3) for n in THRUSTER_NAMES],
                "nav": None if nav is None else [_r(nav["value"][k]) for k in ("x_m", "y_m", "vx_m_s", "vy_m_s")]
                + [_r(rec["t"] - nav["timestamp"], 3)],
                "att": None if att is None else [_r(att["value"]["heading_rad"]), _r(att["value"]["angular_rate_rad_s"])],
                "fuel": None if fuel is None else _r(fuel["value"]["fuel_kg"]),
                "dock": None if dock is None else {k: (_r(v) if isinstance(v, float) else v) for k, v in dock.items()},
                "health": [tr["thruster_health"][n] for n in THRUSTER_NAMES],
                "ver": [ctrl["health_verified"][n] for n in THRUSTER_NAMES],
                "cmd": [_r(ctrl["command"]["throttle"][n], 3) for n in THRUSTER_NAMES],
                "res": _r(ctrl["monitor_residual_m_s"], 4),
                # Per sensor: [seconds since last reading, available, stated 1-sigma].
                "sens": {
                    src: [_r(rec["t"] - o["timestamp"], 2), o["available"],
                          None if not o["uncertainty"] else _r(next(iter(o["uncertainty"].values())), 4)]
                    for src, o in last_seen.items()
                },
                "est": [_r(ctrl["health_estimate"][n], 3) for n in THRUSTER_NAMES],
                "events": pending_events,
            })
            pending_events = []
    return frames


def describe_faults(faults):
    """Short label for a scenario's faults, e.g. 'left lost' or 'forward at 40%'."""
    lost = [f["thruster"] for f in faults if f["type"] == "thruster" and f["effectiveness"] == 0]
    weak = [f"{f['thruster']} at {round(100 * f['effectiveness'])}%" for f in faults
            if f["type"] == "thruster" and f["effectiveness"] > 0]
    parts = ([f"{'+'.join(lost)} lost"] if lost else []) + weak
    return ", ".join(parts) or "no faults"


def build_replay(run_dir, scenarios=None):
    """Write replay.html for a run. scenarios, if given, is a list of
    {"name", "href", "label"} entries for the scenario picker in the header;
    href is relative to this run directory."""
    run_dir = Path(run_dir)
    config = json.loads((run_dir / "config.json").read_text())
    summary = json.loads((run_dir / "summary.json").read_text())
    data = {
        "summary": {k: v for k, v in summary.items() if k != "out_dir"},
        "frame_period_s": config["scenario"]["controller_period_s"],
        "mission": config["mission"],
        "station": config["station"]["components"],
        "orbit_period_s": config["orbit"]["period_s"],
        "docking": config["docking"],
        "max_thrust_n": [config["vehicle"]["thrusters"][n]["max_thrust_n"] for n in THRUSTER_NAMES],
        "monitor_threshold_m_s": config["recovery"]["monitor_threshold_m_s"],
        "usable_effectiveness": config["recovery"]["usable_effectiveness"],
        "sensor_period_s": {
            {"attitude": "attitude_sensor", "navigation": "navigation", "fuel": "fuel_monitor"}[k]: v["period_s"]
            for k, v in config["sensors"].items()
        },
        "initial_fuel_kg": config["initial_state"]["fuel_kg"],
        "frames": build_frames(run_dir / "log.jsonl"),
        "scenarios": scenarios or [],
    }
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text().replace("__REPLAY_DATA__", payload)
    out = run_dir / "replay.html"
    out.write_text(html)
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m singularos_sim.replay <run_dir>", file=sys.stderr)
        return 2
    print(build_replay(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
