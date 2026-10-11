import json
import math
from pathlib import Path

import pytest

from navigation.deadline import time_to_altitude
from simulation.orbit import MU
from singularos_sim.config import controller_spec, default_scenario_path, load_config, with_seed
from singularos_sim.dynamics import Command, Vehicle
from singularos_sim.orbit import (
    REENTRY_ALTITUDE_KM, cw_free_drift, free_drift, inertial_state_km, mean_motion, natural_accel,
    station_radius_m,
)
from singularos_sim.planner import assess_orbital, available_delta_v
from singularos_sim.runner import run_scenario

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"
ORBITAL_SCENARIOS = ("orbital_base", "orbital_strike_return", "orbital_strike_safe_orbit", "orbital_strike_abort")


def read_log(out_dir):
    with open(Path(out_dir) / "log.jsonl") as f:
        return [json.loads(line) for line in f]


@pytest.fixture(scope="module")
def nominal_config():
    return load_config(default_scenario_path())


@pytest.fixture(scope="module")
def n(nominal_config):
    return mean_motion(nominal_config["orbit"]["period_s"])


@pytest.fixture(scope="module")
def orbital_runs(tmp_path_factory):
    runs = {}
    for name in ORBITAL_SCENARIOS:
        config = load_config(SCENARIOS / f"{name}.toml")
        out = tmp_path_factory.mktemp(name)
        runs[name] = (config, run_scenario(config, out), read_log(out))
    return runs


# ------------------------------------------------------------------ dynamics


def test_station_orbit_matches_period(n):
    R = station_radius_m(n)
    assert 6.7e6 < R < 6.9e6
    assert math.isclose(2 * math.pi * math.sqrt(R**3 / (MU * 1e9)), 2 * math.pi / n, rel_tol=1e-12)


def test_nonlinear_accel_reduces_to_cw_near_station(n):
    for x, y, vx, vy in ((1.0, 0.0, 0.0, 0.0), (0.0, 5.0, 0.01, -0.02), (-20.0, 10.0, 0.05, 0.0)):
        ax, ay = natural_accel(n, x, y, vx, vy)
        cx, cy = 3 * n * n * x + 2 * n * vy, -2 * n * vx
        assert abs(ax - cx) < 1e-9 and abs(ay - cy) < 1e-9


def test_nonlinear_drift_diverges_from_cw_at_orbit_scale(n):
    # 150 m/s retrograde, near the time it reaches 120 km: ~290 km from the
    # station, where the linear model is off by ~2.5 km, mostly in altitude.
    state = (0.0, 0.0, 0.0, -150.0)
    nl = free_drift(n, *state, 1400.0)
    cw = cw_free_drift(n, *state, 1400.0)
    assert math.hypot(nl[0], nl[1]) > 250000.0
    assert math.hypot(nl[0] - cw[0], nl[1] - cw[1]) > 2000.0
    assert abs(nl[0] - cw[0]) > 1500.0


def test_nonlinear_drift_conserves_two_body_invariants(n):
    def invariants(s):
        r, v = inertial_state_km(n, *s)
        energy = (v[0] ** 2 + v[1] ** 2) / 2 - MU / math.hypot(r[0], r[1])
        h = r[0] * v[1] - r[1] * v[0]
        return energy, h

    start = (3000.0, -50000.0, 20.0, -150.0)
    e0, h0 = invariants(start)
    e1, h1 = invariants(free_drift(n, *start, 3000.0))
    assert abs(e1 - e0) < 1e-9 * abs(e0)
    assert abs(h1 - h0) < 1e-9 * abs(h0)


def test_unpowered_vehicle_reenters_when_deadline_predicts(nominal_config, n):
    config = with_seed(nominal_config, None)
    config["initial_state"].update(x_m=0.0, y_m=0.0, vx_m_s=0.0, vy_m_s=-150.0)
    vehicle = Vehicle(config)
    predicted = time_to_altitude(*inertial_state_km(n, 0.0, 0.0, 0.0, -150.0), REENTRY_ALTITUDE_KM)
    dt = config["scenario"]["sim_dt_s"]
    R = station_radius_m(n)
    t = 0.0
    while math.hypot(R + vehicle.state.x_m, vehicle.state.y_m) / 1e3 - 6378.137 > REENTRY_ALTITUDE_KM:
        vehicle.step(Command.idle())
        t += dt
        assert t < 2 * predicted
    assert abs(t - predicted) < 2.0


# ------------------------------------------------------------------ deadline


def test_deadline_agrees_from_any_point_on_the_orbit(n):
    start = (0.0, 0.0, 0.0, -300.0)
    t0 = time_to_altitude(*inertial_state_km(n, *start), REENTRY_ALTITUDE_KM)
    later = free_drift(n, *start, 400.0)
    t1 = time_to_altitude(*inertial_state_km(n, *later), REENTRY_ALTITUDE_KM)
    assert abs((t0 - 400.0) - t1) < 0.5


def test_deadline_none_for_safe_orbit(n):
    assert time_to_altitude(*inertial_state_km(n, 0.0, 0.0, 0.0, 0.0), REENTRY_ALTITUDE_KM) is None


# ------------------------------------------------------------------- planner


def orbital_inputs(config, fuel_kg, dv):
    spec = controller_spec(config)
    health = {k: 1.0 for k in spec["max_thrust_n"]}
    nav = {"x_m": 0.0, "y_m": 0.0, "vx_m_s": 0.0, "vy_m_s": -dv}
    mass = spec["dry_mass_kg"] + fuel_kg
    return spec, health, fuel_kg, mass, nav


@pytest.mark.parametrize("fuel_kg, dv, decision", [
    (20.0, 0.5, None),            # small knock: perigee stays safe
    (20.0, 150.0, "BRAKE"),
    (3.2, 150.0, "SAFE_ORBIT"),
    (3.2, 300.0, "ABORT"),
    (0.5, 150.0, "ABORT"),
])
def test_orbital_triage_decisions(n, fuel_kg, dv, decision):
    config = load_config(SCENARIOS / "orbital_base.toml")
    spec, health, fuel, mass, nav = orbital_inputs(config, fuel_kg, dv)
    result = assess_orbital(spec, health, fuel, mass, n, nav, config["recovery"], config["orbital"])
    assert (result and result["decision"]) == decision


def test_available_delta_v_uses_rocket_equation():
    config = load_config(SCENARIOS / "orbital_base.toml")
    spec = controller_spec(config)
    health = {k: 1.0 for k in spec["max_thrust_n"]}
    dv = available_delta_v(spec, health, set(health), 20.0, 70.0, 0.1)
    assert math.isclose(dv, 2500.0 * math.log(70.0 / 50.1), rel_tol=1e-12)
    health["forward"] = 0.5  # degraded thruster: worse effective exhaust velocity
    assert available_delta_v(spec, health, set(health), 20.0, 70.0, 0.1) < dv


def test_orbital_config_rejects_unknown_keys(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text(f'extends = "{(SCENARIOS / "nominal.toml").as_posix()}"\n[orbital]\nsafe_perigee = 150.0\n')
    with pytest.raises(ValueError, match="unknown keys"):
        load_config(path)


# ----------------------------------------------------------------- scenarios


@pytest.mark.parametrize("name", ORBITAL_SCENARIOS)
def test_orbital_scenario_reaches_expected_outcome_safely(orbital_runs, name):
    config, summary, _ = orbital_runs[name]
    assert summary["outcome"] == config["scenario"]["expected_outcome"]
    assert summary["collision"] is None
    if summary["outcome"] == "DOCKED":
        assert summary["truth_docking_check"]["pass"]


def test_orbital_base_has_no_false_alarm(orbital_runs):
    _, summary, _ = orbital_runs["orbital_base"]
    assert summary["investigations"] == 0 and summary["orbital_triage"] is None


def test_strike_return_brakes_returns_from_far_and_docks(orbital_runs):
    _, summary, log = orbital_runs["orbital_strike_return"]
    assert summary["orbital_triage"]["decision"] == "BRAKE"
    assert summary["detection_latency_s"] <= 2.0
    assert summary["investigations"] == 1
    assert summary["plan"]["decision"] == "RETURN" and "far_approach_m" in summary["plan"]
    for h in summary["health_estimate_vs_truth"].values():
        assert h["estimate"] == h["truth"]
    farthest = max(math.hypot(r["truth"]["x_m"], r["truth"]["y_m"]) for r in log)
    assert farthest > 10000.0
    assert summary["orbit_at_end"]["perigee_km"] > 390.0
    assert summary["reentry"] is None


def test_strike_safe_orbit_holds_with_validated_perigee(orbital_runs):
    config, summary, log = orbital_runs["orbital_strike_safe_orbit"]
    triage = summary["orbital_triage"]
    assert triage["decision"] == "SAFE_ORBIT"
    assert triage["safe_orbit_safety"]["authorized"]
    assert summary["hold_kind"] == "safe_orbit"
    safe = config["orbital"]["safe_perigee_km"]
    assert summary["orbit_at_end"]["perigee_km"] >= safe
    assert summary["reentry"] is None and summary["post_outcome_observed_s"] >= 599.0
    # Truth perigee stays safe for the whole observation after HOLD.
    after = [r["truth"]["orbit"]["perigee_km"] for r in log if "orbit" in r["truth"] and r["t"] >= summary["outcome_t"]]
    assert after and min(after) >= safe


def test_strike_abort_reports_deadline_and_reenters(orbital_runs):
    _, summary, _ = orbital_runs["orbital_strike_abort"]
    triage = summary["orbital_triage"]
    assert triage["decision"] == "ABORT"
    assert not triage["safe_orbit_safety"]["authorized"]
    assert triage["time_to_reentry_s"] is not None
    assert summary["reentry"] is not None
    # Abort braking raises perigee somewhat, so reentry comes after the
    # forecast made at triage, but in the same range.
    forecast = summary["anomaly_detected_t"] + triage["time_to_reentry_s"]
    assert forecast <= summary["reentry"]["t"] <= forecast * 1.25
