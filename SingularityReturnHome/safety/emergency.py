import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from simulation.orbit import MU, EARTH_RADIUS, orbital_status
from math import sqrt

MIN_SAFE_PERIGEE_KM = 200.0

def assess(position, velocity, communications):
    orbit = orbital_status(position, velocity)
    hazards = []

    if orbit["perigee_km"] < MIN_SAFE_PERIGEE_KM:
        hazards.append("UNSAFE_PERIGEE")
    if not communications:
        hazards.append("COMMUNICATIONS_LOST")

    return {
        "emergency": bool(hazards),
        "hazards": hazards,
        "orbit": orbit,
    }

if __name__ == "__main__":
    r = EARTH_RADIUS + 400
    position = (r, 0, 0)
    velocity = (0, sqrt(MU / r) - 0.15, 0)
    result = assess(position, velocity, communications=False)
    print(result)
