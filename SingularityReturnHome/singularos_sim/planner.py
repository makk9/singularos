"""Recovery planner and validator for the deterministic baseline.

A pure function of controller-side information only: estimated thruster
health from diagnostics, observed fuel, observed position and the nominal
vehicle spec. It never sees truth.

Baseline capability (documented for MISSION.md section 11 comparisons):
  - Docking requires both axial thrusters (forward and backward) to be usable,
    so closing speed can be controlled in both directions with the nose on the
    dock axis. The baseline has no coast-in or other docking procedure for a
    lost axial thruster.
  - Transit with one lateral or axial thruster lost is handled by rotating so
    an intact opposing pair is aligned with the direction of travel.
  - HOLD (station-keeping at a safe point) requires at least one intact
    opposing pair (forward/backward or left/right): turning that pair toward
    each push it needs reaches any direction, as the degraded transit does.
  - Fuel: the return must fit within observed fuel minus a reserve, with a
    safety margin on the estimate.

Orbit-scale triage (assess_orbital): when an anomaly leaves the vehicle on
an orbit whose perigee is below orbital.safe_perigee_km, the first response
is decided from the vehicle's own orbit and its delta-v budget, in order:
  BRAKE       null the velocity relative to the station (which restores the
              station's safe orbit), then diagnose and plan as usual.
  SAFE_ORBIT  a prograde burn that raises perigee to a safe altitude
              (guidance.recovery.plan_recovery), authorised only if
              safety.validator.validate_independently re-verifies it within
              the available delta-v. The vehicle then holds in that orbit.
  ABORT       neither fits; navigation.deadline.time_to_altitude reports the
              time left before reentry.
Delta-v budget: rocket equation with the worst effective exhaust velocity
(max thrust / fuel rate) among usable thrusters, on observed fuel minus the
reserve.
"""

import math

from guidance.recovery import plan_recovery
from navigation.deadline import time_to_altitude
from safety.validator import validate_independently

from .config import THRUSTER_NAMES
from .orbit import REENTRY_ALTITUDE_KM, inertial_state_km, orbit_status

PAIRS = (("forward", "backward"), ("left", "right"))


def usable(health, threshold):
    return {name for name in THRUSTER_NAMES if health[name] >= threshold}


def path_length(start, points):
    total, prev = 0.0, start
    for p in points:
        total += math.hypot(p[0] - prev[0], p[1] - prev[1])
        prev = p
    return total


def estimate_return_fuel(spec, health, usable_set, mass, legs, cruise_speed, current_speed, approach_speed,
                         extra_delta_v=0.0):
    """Fuel estimate for a stop-at-every-waypoint return.

    Each leg accelerates to cruise and brakes to rest; the current velocity is
    nulled first; final approach adds one more accelerate/brake at approach
    speed. Uses the worst fuel cost per newton-second among usable thrusters,
    accounting for reduced effectiveness. Rotation adds two rate changes of
    the maximum rate per leg. extra_delta_v covers legs flown at another
    speed (the far-range approach).
    """
    delta_v = current_speed + legs * 2.0 * cruise_speed + 2.0 * approach_speed + extra_delta_v
    cost_per_ns = max(
        spec["fuel_rate_kg_s"][n] / (spec["max_thrust_n"][n] * health[n]) for n in usable_set
    )
    rotation = (legs + 1) * 2.0 * spec["max_rate_rad_s"] * spec["rotation_fuel_kg_per_rad_s"]
    return mass * delta_v * cost_per_ns + rotation


def assess_recovery(spec, health, fuel_kg, mass, return_legs, params, current_speed, extra_delta_v=0.0):
    """Decide RETURN (and dock), HOLD or ABORT. Returns a dict with the
    decision, the reasons, and the numbers behind them."""
    p = params
    usable_set = usable(health, p["usable_effectiveness"])
    reasons = []
    has_pair = any(a in usable_set and b in usable_set for a, b in PAIRS)

    needed = None
    dock_ok = "forward" in usable_set and "backward" in usable_set
    if not dock_ok:
        missing = [n for n in ("forward", "backward") if n not in usable_set]
        reasons.append(f"docking infeasible: axial thruster(s) unusable: {', '.join(missing)}")
    if dock_ok:
        needed = estimate_return_fuel(spec, health, usable_set, mass, return_legs, p["transit_max_speed_m_s"],
                                      current_speed, p["approach_max_speed_m_s"], extra_delta_v)
        budget = fuel_kg - p["fuel_reserve_kg"]
        if needed * p["fuel_margin"] > budget:
            dock_ok = False
            reasons.append(f"docking infeasible: return needs {needed:.3f} kg x{p['fuel_margin']} margin, "
                           f"budget {budget:.3f} kg after reserve")
        else:
            reasons.append(f"return fuel {needed:.3f} kg x{p['fuel_margin']} margin within budget {budget:.3f} kg")

    if dock_ok:
        decision = "RETURN"
    elif has_pair and fuel_kg > p["fuel_reserve_kg"]:
        decision = "HOLD"
        reasons.append("hold feasible: an intact opposing thruster pair and fuel above reserve")
    else:
        decision = "ABORT"
        reasons.append("hold infeasible: needs an intact opposing thruster pair and fuel above reserve")

    return {
        "decision": decision,
        "reasons": reasons,
        "usable": sorted(usable_set, key=THRUSTER_NAMES.index),
        "return_legs": return_legs,
        "fuel_needed_kg": needed,
        "fuel_observed_kg": fuel_kg,
    }


def available_delta_v(spec, health, usable_set, fuel_kg, mass, reserve_kg):
    """Delta-v (m/s) obtainable from observed fuel above the reserve."""
    burnable = max(0.0, fuel_kg - reserve_kg)
    exhaust = [spec["max_thrust_n"][n] * health[n] / spec["fuel_rate_kg_s"][n]
               for n in usable_set if spec["fuel_rate_kg_s"][n] > 0]
    if not exhaust or burnable <= 0 or mass - burnable <= 0:
        return 0.0
    return min(exhaust) * math.log(mass / (mass - burnable))


def assess_orbital(spec, health, fuel_kg, mass, n, nav, params, orbital):
    """Orbit-scale first response from an observed station-frame state.

    Returns None while perigee is safe; otherwise a dict with the decision
    (BRAKE, SAFE_ORBIT or ABORT), the reasons and the numbers behind them."""
    state = (nav["x_m"], nav["y_m"], nav["vx_m_s"], nav["vy_m_s"])
    status = orbit_status(n, *state)
    if status["perigee_km"] >= orbital["safe_perigee_km"]:
        return None

    usable_set = usable(health, params["usable_effectiveness"])
    budget = available_delta_v(spec, health, usable_set, fuel_kg, mass, params["fuel_reserve_kg"])
    margin = orbital["delta_v_margin"]
    position, velocity = inertial_state_km(n, *state)
    deadline = time_to_altitude(position, velocity, REENTRY_ALTITUDE_KM)
    thrust = min((spec["max_thrust_n"][u] * health[u] for u in usable_set), default=0.0)
    brake_dv = math.hypot(nav["vx_m_s"], nav["vy_m_s"])
    brake_time = brake_dv * mass / thrust if thrust > 0 else math.inf
    reasons = [f"perigee {status['perigee_km']:.1f} km below safe {orbital['safe_perigee_km']:.0f} km"]

    plan = plan_recovery(position, velocity)
    safety = validate_independently(position, velocity, plan, budget / margin)
    result = {
        "orbit": status,
        "time_to_reentry_s": deadline,
        "available_delta_v_m_s": budget,
        "brake_delta_v_m_s": brake_dv,
        "brake_time_s": brake_time,
        "safe_orbit_plan": plan,
        "safe_orbit_safety": safety,
    }

    brake_in_time = deadline is None or brake_time < deadline
    if brake_dv * margin <= budget and brake_in_time:
        decision = "BRAKE"
        reasons.append(f"braking {brake_dv:.1f} m/s x{margin} margin fits {budget:.1f} m/s available"
                       + (f", done in {brake_time:.0f} s of {deadline:.0f} s to reentry" if deadline else ""))
    elif safety["authorized"]:
        decision = "SAFE_ORBIT"
        reasons.append(f"braking needs {brake_dv:.1f} m/s x{margin} margin of {budget:.1f} m/s available"
                       + ("" if brake_in_time else " and would finish after reentry"))
        reasons.append(f"perigee raise of {plan['delta_v_m_s']:.1f} m/s authorised by independent validation")
    else:
        decision = "ABORT"
        reasons.append(f"braking needs {brake_dv:.1f} m/s x{margin} margin of {budget:.1f} m/s available")
        reasons.append("perigee raise rejected: " + ", ".join(safety["reasons"]))
        if deadline is not None:
            reasons.append(f"reentry in {deadline:.0f} s")
    return {"decision": decision, "reasons": reasons, **result}
