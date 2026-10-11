"""Orbital relative motion about the station, valid from metres to orbit scale.

The station is on a circular Earth orbit with mean motion n = 2 pi / period,
at radius R = (MU / n^2)^(1/3). Motion is in-plane, in the station-centred
rotating frame:
  +x  radial, away from Earth (R-bar)
  +y  along-track, the direction of orbital motion (V-bar)

The vehicle obeys two-body gravity. In the rotating frame its acceleration is
the exact nonlinear equation of relative motion:

  x'' =  2 n y' + n^2 (R + x) - MU (R + x) / r^3 + a_x
  y'' = -2 n x' + n^2 y       - MU y       / r^3 + a_y

with r = |(R + x, y)| the vehicle's distance from Earth's centre and a the
applied acceleration (thrust, impacts). Since MU / R^3 = n^2, the gravity and
centrifugal terms combine to n^2 (R + x, y) (1 - (R / r)^3), which is
evaluated with log1p/expm1 so it stays accurate at metre offsets from a
6,800 km radius. Linearising (1 - (R / r)^3) ~ 3 x / R gives the
Clohessy-Wiltshire equations, x'' = 3 n^2 x + 2 n y', y'' = -2 n x'
(cw_free_drift below), which agree to well under a millimetre within tens of
metres of the station but break down at kilometre-plus separations.

Not modelled: out-of-plane motion, Earth's oblateness (J2), atmospheric drag,
third bodies. Reentry is treated as reaching orbit.REENTRY_ALTITUDE_KM.

The station's orbit is public knowledge, so both the simulator and the
controller use these functions.
"""

import math

from simulation.orbit import EARTH_RADIUS, MU, orbital_status

MU_M3_S2 = MU * 1e9
EARTH_RADIUS_M = EARTH_RADIUS * 1e3
REENTRY_ALTITUDE_KM = 120.0


def mean_motion(period_s):
    return 2.0 * math.pi / period_s


def station_radius_m(n):
    """Orbit radius of the station (m) for mean motion n (rad/s)."""
    return (MU_M3_S2 / (n * n)) ** (1.0 / 3.0)


def natural_accel(n, x, y, vx, vy):
    """Acceleration with no thrust, in the station frame (m/s^2)."""
    R = station_radius_m(n)
    rx = R + x
    q = (2.0 * x * R + x * x + y * y) / (R * R)  # (r / R)^2 - 1
    f = -math.expm1(-1.5 * math.log1p(q))  # 1 - (R / r)^3
    n2 = n * n
    return n2 * rx * f + 2.0 * n * vy, n2 * y * f - 2.0 * n * vx


def _deriv(n, s):
    ax, ay = natural_accel(n, *s)
    return (s[2], s[3], ax, ay)


def free_drift(n, x0, y0, vx0, vy0, t, max_step_s=1.0):
    """Unpowered motion under the nonlinear equations: (x, y, vx, vy) at t.

    Fourth-order Runge-Kutta with steps of at most max_step_s."""
    steps = max(1, math.ceil(abs(t) / max_step_s))
    h = t / steps
    s = (x0, y0, vx0, vy0)
    for _ in range(steps):
        k1 = _deriv(n, s)
        k2 = _deriv(n, tuple(a + 0.5 * h * b for a, b in zip(s, k1)))
        k3 = _deriv(n, tuple(a + 0.5 * h * b for a, b in zip(s, k2)))
        k4 = _deriv(n, tuple(a + h * b for a, b in zip(s, k3)))
        s = tuple(a + h / 6.0 * (b1 + 2 * b2 + 2 * b3 + b4) for a, b1, b2, b3, b4 in zip(s, k1, k2, k3, k4))
    return s


def cw_free_drift(n, x0, y0, vx0, vy0, t):
    """Analytic Clohessy-Wiltshire solution (the linearised model): (x, y, vx, vy) at t."""
    s, c = math.sin(n * t), math.cos(n * t)
    x = (4 - 3 * c) * x0 + s / n * vx0 + 2 / n * (1 - c) * vy0
    y = 6 * (s - n * t) * x0 + y0 - 2 / n * (1 - c) * vx0 + (4 * s - 3 * n * t) / n * vy0
    vx = 3 * n * s * x0 + c * vx0 + 2 * s * vy0
    vy = -6 * n * (1 - c) * x0 - 2 * s * vx0 + (4 * c - 3) * vy0
    return x, y, vx, vy


def inertial_state_km(n, x, y, vx, vy):
    """Earth-centred position (km) and velocity (km/s) as 3-vectors.

    Expressed along the rotating frame's axes at this instant: position
    (R + x, y), velocity v + omega x r = (vx - n y, vy + n (R + x))."""
    R = station_radius_m(n)
    position = ((R + x) / 1e3, y / 1e3, 0.0)
    velocity = ((vx - n * y) / 1e3, (vy + n * (R + x)) / 1e3, 0.0)
    return position, velocity


def altitude_km(n, x, y):
    R = station_radius_m(n)
    return (math.hypot(R + x, y) - EARTH_RADIUS_M) / 1e3


def orbit_status(n, x, y, vx, vy):
    """Altitude, speed, eccentricity and perigee altitude of the vehicle's
    own orbit (simulation.orbit.orbital_status), from a station-frame state."""
    return orbital_status(*inertial_state_km(n, x, y, vx, vy))
