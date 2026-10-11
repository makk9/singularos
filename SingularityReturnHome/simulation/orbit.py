from math import sqrt

MU = 398600.4418
EARTH_RADIUS = 6378.137

def orbital_status(position, velocity):
    r = sqrt(sum(x*x for x in position))
    v2 = sum(x*x for x in velocity)
    energy = v2 / 2 - MU / r
    h = (
        position[1]*velocity[2] - position[2]*velocity[1],
        position[2]*velocity[0] - position[0]*velocity[2],
        position[0]*velocity[1] - position[1]*velocity[0],
    )
    h2 = sum(x*x for x in h)
    eccentricity = sqrt(max(0, 1 + 2*energy*h2/MU**2))
    perigee = h2 / (MU * (1 + eccentricity)) - EARTH_RADIUS
    return {
        "altitude_km": round(r-EARTH_RADIUS, 2),
        "speed_km_s": round(sqrt(v2), 4),
        "eccentricity": round(eccentricity, 6),
        "perigee_km": round(perigee, 2),
    }

if __name__ == "__main__":
    r = EARTH_RADIUS + 400
    position = (r, 0, 0)
    velocity = (0, sqrt(MU/r), 0)
    print("NOMINAL:", orbital_status(position, velocity))
    disturbed = (0, velocity[1] - 0.15, 0)
    print("DISTURBED:", orbital_status(position, disturbed))
