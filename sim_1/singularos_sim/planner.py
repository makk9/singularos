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
"""

import math

from .config import THRUSTER_NAMES

PAIRS = (("forward", "backward"), ("left", "right"))


def usable(health, threshold):
    return {name for name in THRUSTER_NAMES if health[name] >= threshold}


def path_length(start, points):
    total, prev = 0.0, start
    for p in points:
        total += math.hypot(p[0] - prev[0], p[1] - prev[1])
        prev = p
    return total


def estimate_return_fuel(spec, health, usable_set, mass, legs, cruise_speed, current_speed, approach_speed):
    """Fuel estimate for a stop-at-every-waypoint return.

    Each leg accelerates to cruise and brakes to rest; the current velocity is
    nulled first; final approach adds one more accelerate/brake at approach
    speed. Uses the worst fuel cost per newton-second among usable thrusters,
    accounting for reduced effectiveness. Rotation adds two rate changes of
    the maximum rate per leg.
    """
    delta_v = current_speed + legs * 2.0 * cruise_speed + 2.0 * approach_speed
    cost_per_ns = max(
        spec["fuel_rate_kg_s"][n] / (spec["max_thrust_n"][n] * health[n]) for n in usable_set
    )
    rotation = (legs + 1) * 2.0 * spec["max_rate_rad_s"] * spec["rotation_fuel_kg_per_rad_s"]
    return mass * delta_v * cost_per_ns + rotation


def assess_recovery(spec, health, fuel_kg, mass, return_legs, params, current_speed):
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
                                      current_speed, p["approach_max_speed_m_s"])
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
