from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from guidance.recovery import plan_recovery
from simulation.orbit import MU, EARTH_RADIUS
from math import sqrt, isfinite

MAX_DELTA_V_M_S = 150.0
AVAILABLE_DELTA_V_M_S = 120.0
MIN_PERIGEE_KM = 199.9  # Numerical tolerance for rounded output

def validate(plan, available_delta_v_m_s=AVAILABLE_DELTA_V_M_S):
    reasons = []

    if plan.get("status") != "PROPOSED":
        reasons.append("INVALID_PLAN")
        return {"authorized": False, "reasons": reasons}

    delta_v = plan["delta_v_m_s"]
    perigee = plan["predicted_orbit"]["perigee_km"]

    if not all(isfinite(x) for x in (delta_v, perigee)):
        reasons.append("NONFINITE_VALUE")
    if delta_v < 0 or delta_v > MAX_DELTA_V_M_S:
        reasons.append("MANEUVER_LIMIT_EXCEEDED")
    if delta_v > available_delta_v_m_s:
        reasons.append("INSUFFICIENT_FUEL")
    if perigee < MIN_PERIGEE_KM:
        reasons.append("UNSAFE_RECOVERY_ORBIT")

    return {"authorized": not reasons, "reasons": reasons}

if __name__ == "__main__":
    r = EARTH_RADIUS + 400
    position = (r, 0, 0)
    velocity = (0, sqrt(MU/r) - 0.15, 0)
    plan = plan_recovery(position, velocity)
    print("PLAN:", plan)
    print("SAFETY:", validate(plan))

def validate_independently(position, velocity, plan, available_delta_v_m_s=AVAILABLE_DELTA_V_M_S):
    from simulation.orbit import orbital_status
    from math import sqrt

    initial = validate(plan, available_delta_v_m_s)
    if not initial["authorized"]:
        return initial

    speed = sqrt(sum(v*v for v in velocity))
    if speed <= 0:
        return {"authorized": False, "reasons": ["INVALID_VELOCITY"]}

    dv = plan["delta_v_m_s"] / 1000
    new_velocity = tuple(v * (1 + dv/speed) for v in velocity)
    verified = orbital_status(position, new_velocity)

    if verified["perigee_km"] < MIN_PERIGEE_KM:
        return {"authorized": False, "reasons": ["VERIFIED_PERIGEE_UNSAFE"]}

    return {
        "authorized": True,
        "reasons": [],
        "verified_orbit": verified
    }

if __name__ == "__main__":
    print("INDEPENDENT:", validate_independently(position, velocity, plan))
