from math import acos, atan2, pi, sin, sqrt
from simulation.orbit import MU, EARTH_RADIUS


def time_to_altitude(position, velocity, altitude_km=120):
    """Time in seconds until the next descending crossing of altitude_km.

    Two-body elliptical orbit; position in km, velocity in km/s, from any
    point on the orbit. Returns 0.0 if already at or below the altitude, and
    None when the orbit never descends through it (circular, hyperbolic, or
    perigee above the target).
    """
    r = sqrt(sum(x*x for x in position))
    v2 = sum(x*x for x in velocity)
    rv = sum(p*v for p, v in zip(position, velocity))
    target = EARTH_RADIUS + altitude_km

    if r <= target:
        return 0.0
    if v2 <= 0:
        return None

    a_inverse = 2/r - v2/MU
    if a_inverse <= 0:
        return None
    a = 1/a_inverse

    # Eccentricity vector: ((v^2 - MU/r) r - (r.v) v) / MU
    e_vec = [((v2 - MU/r)*p - rv*v) / MU for p, v in zip(position, velocity)]
    e = sqrt(sum(x*x for x in e_vec))
    if not (1e-9 < e < 1):
        return None

    perigee = a*(1-e)
    if target < perigee:
        return None

    # Current eccentric and mean anomaly.
    E = atan2(rv / sqrt(MU*a), 1 - r/a) % (2*pi)
    M = E - e*sin(E)
    # Descending crossing lies on the branch E in (pi, 2 pi).
    E_t = 2*pi - acos(max(-1.0, min(1.0, (1-target/a)/e)))
    M_t = E_t - e*sin(E_t)
    n = sqrt(MU/a**3)

    return ((M_t - M) % (2*pi))/n
