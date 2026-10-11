from pathlib import Path
import sys
from math import sqrt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.orbit import MU, EARTH_RADIUS, orbital_status
from guidance.recovery import plan_recovery
from safety.validator import validate_independently

def execute(position, velocity, plan):
    authorization = validate_independently(position, velocity, plan)

    if not authorization["authorized"]:
        return {"status": "REJECTED", "safety": authorization}

    speed = sqrt(sum(v*v for v in velocity))
    dv = plan["delta_v_m_s"] / 1000
    new_velocity = tuple(v * (1 + dv/speed) for v in velocity)

    return {
        "status": "SIMULATED_BURN_COMPLETE",
        "delta_v_m_s": plan["delta_v_m_s"],
        "resulting_orbit": orbital_status(position, new_velocity),
    }

if __name__ == "__main__":
    r = EARTH_RADIUS + 400
    position = (r, 0, 0)
    velocity = (0, sqrt(MU/r) - 0.15, 0)

    plan = plan_recovery(position, velocity)
    print("BEFORE:", orbital_status(position, velocity))
    print("EXECUTION:", execute(position, velocity, plan))
