from math import sqrt
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from simulation.orbit import MU, EARTH_RADIUS, orbital_status

TARGET_PERIGEE_KM = 200.0

def plan_recovery(position, velocity):
    r = sqrt(sum(x*x for x in position))
    speed = sqrt(sum(v*v for v in velocity))
    target_rp = EARTH_RADIUS + TARGET_PERIGEE_KM

    if speed <= 0 or r <= target_rp:
        return {"status": "NO_VALID_PLAN"}

    target_speed = sqrt(2 * MU * target_rp / (r * (r + target_rp)))
    delta_v = max(0.0, target_speed - speed)

    direction = tuple(v / speed for v in velocity)
    recovered_velocity = tuple(
        v + delta_v * d for v, d in zip(velocity, direction)
    )

    return {
        "status": "PROPOSED",
        "delta_v_m_s": round(delta_v * 1000, 2),
        "predicted_orbit": orbital_status(position, recovered_velocity),
    }

if __name__ == "__main__":
    r = EARTH_RADIUS + 400
    position = (r, 0, 0)
    velocity = (0, sqrt(MU/r) - 0.15, 0)
    print(plan_recovery(position, velocity))
