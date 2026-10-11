import json
import math
from pathlib import Path

import pytest

from singularos_sim import controller as controller_module
from singularos_sim.config import default_scenario_path, load_config, with_seed
from singularos_sim.dynamics import wrap_angle
from singularos_sim.replay import build_replay
from singularos_sim.runner import run_scenario


def read_log(out_dir):
    with open(Path(out_dir) / "log.jsonl") as f:
        return [json.loads(line) for line in f]


@pytest.fixture(scope="module")
def nominal_config():
    return load_config(default_scenario_path())


@pytest.fixture(scope="module")
def nominal_run(nominal_config, tmp_path_factory):
    out = tmp_path_factory.mktemp("nominal")
    summary = run_scenario(nominal_config, out)
    return summary, read_log(out)


def test_same_seed_gives_identical_log(nominal_config, tmp_path):
    config = with_seed(nominal_config, 7)
    run_scenario(config, tmp_path / "a")
    run_scenario(config, tmp_path / "b")
    log_a = (tmp_path / "a" / "log.jsonl").read_bytes()
    log_b = (tmp_path / "b" / "log.jsonl").read_bytes()
    assert log_a == log_b

    run_scenario(with_seed(nominal_config, 8), tmp_path / "c")
    assert (tmp_path / "c" / "log.jsonl").read_bytes() != log_a


def test_truth_position_and_heading_are_continuous(nominal_config, nominal_run):
    _, log = nominal_run
    dt = nominal_config["scenario"]["sim_dt_s"]
    max_rate = nominal_config["vehicle"]["attitude"]["max_rate_rad_s"]
    for prev, cur in zip(log, log[1:]):
        a, b = prev["truth"], cur["truth"]
        moved = math.hypot(b["x_m"] - a["x_m"], b["y_m"] - a["y_m"])
        speed = max(math.hypot(a["vx_m_s"], a["vy_m_s"]), math.hypot(b["vx_m_s"], b["vy_m_s"]))
        assert moved <= speed * dt + 1e-9, f"position jump at step {cur['step']}"
        turned = abs(wrap_angle(b["heading_rad"] - a["heading_rad"]))
        assert turned <= max_rate * dt + 1e-12, f"heading jump at step {cur['step']}"


def test_nominal_scenario_docks(nominal_run):
    summary, log = nominal_run
    assert summary["outcome"] == "DOCKED"
    assert summary["truth_docking_check"]["pass"]
    phases = [r["controller"]["phase"] for r in log if "controller" in r]
    seen = list(dict.fromkeys(phases))
    assert seen == ["DEPART", "INSPECT", "RETURN", "APPROACH", "DOCKED"]


def test_fuel_never_negative_nominal(nominal_run):
    _, log = nominal_run
    fuel = [r["truth"]["fuel_kg"] for r in log]
    assert min(fuel) >= 0.0
    assert all(b <= a for a, b in zip(fuel, fuel[1:]))


def test_fuel_never_negative_when_exhausted(nominal_config, tmp_path):
    config = with_seed(nominal_config, None)
    config["initial_state"]["fuel_kg"] = 0.02
    config["scenario"]["max_duration_s"] = 200.0
    summary = run_scenario(config, tmp_path)
    fuel = [r["truth"]["fuel_kg"] for r in read_log(tmp_path)]
    assert fuel[-1] == 0.0
    assert min(fuel) >= 0.0
    # Running dry shows up as thrust not matching commands; the controller
    # investigates and must not report a dock.
    assert summary["outcome"] in ("ABORT", "HOLD", "NOT_DOCKED")


def test_observations_follow_contract(nominal_run):
    _, log = nominal_run
    sources = set()
    for r in log:
        for obs in r["observations"]:
            assert set(obs) == {"source", "timestamp", "available", "value", "uncertainty"}
            assert obs["timestamp"] == r["t"]
            sources.add(obs["source"])
    assert sources == {"attitude_sensor", "navigation", "fuel_monitor"}


def test_controller_has_no_access_to_truth():
    source = Path(controller_module.__file__).read_text()
    for name in ("TruthState", "Vehicle", "runner", "sensors"):
        assert name not in source


def test_replay_embeds_one_frame_per_controller_tick(nominal_config, tmp_path):
    run_scenario(nominal_config, tmp_path)
    html = build_replay(tmp_path).read_text()
    start = html.index('<script id="data" type="application/json">') + len('<script id="data" type="application/json">')
    data = json.loads(html[start:html.index("</script>", start)])
    ticks = [r for r in read_log(tmp_path) if "controller" in r]
    assert len(data["frames"]) == len(ticks)
    assert data["frames"][-1]["phase"] == "DOCKED"


def test_nominal_inspects_every_stop_without_collision(nominal_config, nominal_run):
    summary, log = nominal_run
    stops = [r["name"] for r in nominal_config["mission"]["route"] if r["kind"] == "inspect"]
    assert summary["inspections_completed"] == stops
    assert summary["collision"] is None
    assert summary["min_clearance_in_flight"]["clearance_m"] > 2.0
    assert min(r["truth"]["station_clearance_m"] for r in log) > 0.0


def test_route_through_station_is_reported_as_collision(nominal_config, tmp_path):
    config = with_seed(nominal_config, None)
    # Fly straight from staging to the far side of the station, through the hull.
    config["mission"]["route"] = [
        {"kind": "inspect", "name": "Radiator", "target": "Radiator",
         "point_m": [-20.0, 0.0], "look_at_m": [-14.0, 0.0], "hold_s": 1.0},
    ]
    config["scenario"]["max_duration_s"] = 300.0
    summary = run_scenario(config, tmp_path)
    assert summary["collision"] is not None
    assert summary["collision"]["component"] in {"Core module", "Radiator"}


# ---------------------------------------------------------------- milestone 2

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"
FAULT_SCENARIOS = ("thruster_fault", "thruster_degraded", "thruster_fault_infeasible",
                   "thruster_fault_two_lateral", "thruster_fault_two_axial", "thruster_fault_abort")


@pytest.fixture(scope="module")
def fault_runs(tmp_path_factory):
    runs = {}
    for name in FAULT_SCENARIOS:
        config = load_config(SCENARIOS / f"{name}.toml")
        out = tmp_path_factory.mktemp(name)
        runs[name] = (config, run_scenario(config, out), read_log(out))
    return runs


@pytest.mark.parametrize("name", FAULT_SCENARIOS)
def test_fault_scenario_reaches_expected_outcome_safely(fault_runs, name):
    config, summary, _ = fault_runs[name]
    assert summary["outcome"] == config["scenario"]["expected_outcome"]
    assert summary["collision"] is None
    if summary["outcome"] == "DOCKED":
        assert summary["truth_docking_check"]["pass"]


@pytest.mark.parametrize("name", FAULT_SCENARIOS)
def test_fault_is_detected_quickly_and_diagnosed(fault_runs, name):
    _, summary, _ = fault_runs[name]
    assert summary["detection_latency_s"] is not None and summary["detection_latency_s"] <= 2.0
    for thruster, h in summary["health_estimate_vs_truth"].items():
        assert abs(h["estimate"] - h["truth"]) <= 0.15, thruster


def test_infeasible_fault_never_attempts_docking(fault_runs):
    _, summary, log = fault_runs["thruster_fault_infeasible"]
    phases = {r["controller"]["phase"] for r in log if "controller" in r}
    assert "APPROACH" not in phases
    assert summary["plan"]["decision"] == "HOLD"


def test_nominal_has_no_false_alarm(nominal_run):
    summary, log = nominal_run
    assert summary["investigations"] == 0
    assert all(r["controller"]["phase"] != "INVESTIGATE" for r in log if "controller" in r)


def test_impact_keeps_truth_continuous(fault_runs, nominal_config):
    _, _, log = fault_runs["thruster_fault"]
    dt = nominal_config["scenario"]["sim_dt_s"]
    for prev, cur in zip(log, log[1:]):
        a, b = prev["truth"], cur["truth"]
        moved = math.hypot(b["x_m"] - a["x_m"], b["y_m"] - a["y_m"])
        speed = max(math.hypot(a["vx_m_s"], a["vy_m_s"]), math.hypot(b["vx_m_s"], b["vy_m_s"]))
        assert moved <= speed * dt + 1e-9
    assert any("events" in r["truth"] for r in log)


def test_controller_never_receives_faults_or_true_health():
    from singularos_sim.config import controller_spec

    config = load_config(SCENARIOS / "thruster_fault.toml")
    spec = json.dumps(controller_spec(config))
    assert "effectiveness" not in spec and "faults" not in spec
    source = Path(controller_module.__file__).read_text()
    assert "faults" not in source and "thruster_health" not in source


def test_extends_merges_base_scenario():
    base = load_config(default_scenario_path())
    config = load_config(SCENARIOS / "thruster_fault.toml")
    assert config["scenario"]["name"] == "thruster_fault"
    assert config["station"] == base["station"]
    assert config["scenario"]["sim_dt_s"] == base["scenario"]["sim_dt_s"]
    assert len(config["faults"]) == 2 and base["faults"] == []


def test_planner_decisions(nominal_config):
    from singularos_sim.config import controller_spec
    from singularos_sim.planner import assess_recovery

    spec = controller_spec(nominal_config)
    params = nominal_config["recovery"]

    def decide(health, fuel=1.5):
        h = {"forward": 1.0, "backward": 1.0, "left": 1.0, "right": 1.0, **health}
        return assess_recovery(spec, h, fuel, 51.5, 4, params, 0.0)["decision"]

    assert decide({}) == "RETURN"
    assert decide({"left": 0.0}) == "RETURN"
    assert decide({"forward": 0.4}) == "RETURN"
    assert decide({"backward": 0.0}) == "HOLD"
    assert decide({"forward": 0.0, "backward": 0.0}) == "HOLD"  # left/right pair can hold
    assert decide({"left": 0.0, "right": 0.0}) == "RETURN"
    assert decide({}, fuel=0.12) == "HOLD"
    assert decide({"left": 0.0, "right": 0.0, "backward": 0.0}) == "ABORT"



# ------------------------------------------------------- orbital relative motion


def test_unpowered_truth_matches_cw_near_station(nominal_config):
    from singularos_sim.dynamics import Command, Vehicle
    from singularos_sim.orbit import cw_free_drift, mean_motion

    config = with_seed(nominal_config, None)
    x0, y0, vx0, vy0 = 20.0, -5.0, 0.01, -0.02
    config["initial_state"].update(x_m=x0, y_m=y0, vx_m_s=vx0, vy_m_s=vy0)
    vehicle = Vehicle(config)
    dt = config["scenario"]["sim_dt_s"]
    steps = int(round(1200.0 / dt))
    for _ in range(steps):
        vehicle.step(Command.idle())
    n = mean_motion(config["orbit"]["period_s"])
    x, y, vx, vy = cw_free_drift(n, x0, y0, vx0, vy0, steps * dt)
    s = vehicle.state
    assert math.hypot(s.x_m - x, s.y_m - y) < 0.05
    assert math.hypot(s.vx_m_s - vx, s.vy_m_s - vy) < 1e-4
    # Orbital motion is not negligible over this time: the craft moved metres.
    assert math.hypot(x - x0, y - y0) > 5.0


def test_hold_keeps_station_against_orbital_drift(fault_runs):
    _, summary, _ = fault_runs["thruster_fault_infeasible"]
    assert summary["post_outcome_observed_s"] >= 299.0
    assert summary["hold_max_deviation_m"] < 1.0


def test_abort_brakes_to_safe_then_shuts_down(fault_runs, nominal_config):
    _, summary, log = fault_runs["thruster_fault_abort"]
    assert summary["plan"]["decision"] == "ABORT"
    events = [(r["t"], e) for r in log if "controller" in r for e in r["controller"].get("events", [])]
    t_safe, safe = next((t, e) for t, e in events if e["type"] == "abort_safe")
    assert safe["braked"] and safe["speed_m_s"] <= nominal_config["recovery"]["brake_speed_m_s"]
    at_abort = next(r["truth"] for r in log if r["t"] >= summary["outcome_t"])
    assert math.hypot(at_abort["vx_m_s"], at_abort["vy_m_s"]) > 0.1  # it really had to brake
    after = [r for r in log if r["t"] > t_safe]
    assert after and all(not any(r["truth"]["thrust_n"].values()) for r in after[2:])
    # Unpowered afterwards: orbital motion still moves it.
    start, end = after[0]["truth"], after[-1]["truth"]
    assert math.hypot(end["x_m"] - start["x_m"], end["y_m"] - start["y_m"]) > 1.0
