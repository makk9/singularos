from math import acos, pi, sin, sqrt
from simulation.orbit import MU, EARTH_RADIUS


def time_to_altitude(position, velocity, altitude_km=120):
    """Time in seconds until the next descending altitude crossing.

    Assumes an elliptical two-body orbit and tangential velocity
    at apogee. Returns None when these assumptions do not hold.
    """
    r = sqrt(sum(x*x for x in position))
    v2 = sum(x*x for x in velocity)
    rv = sum(p*v for p, v in zip(position, velocity))

    if abs(rv) > 1e-6 or v2 <= 0:
        return None

    a_inverse = 2/r - v2/MU
    if a_inverse <= 0:
        return None

    a = 1/a_inverse
    e = r/a - 1

    if not (0 < e < 1):
        return None

    target = EARTH_RADIUS + altitude_km
    perigee = a*(1-e)
    if target < perigee or target >= r:
        return None

    E = acos((1-target/a)/e)
    M = E-e*sin(E)
    n = sqrt(MU/a**3)

    return (pi-M)/n
