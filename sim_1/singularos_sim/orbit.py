"""Orbital relative motion near the station (Clohessy-Wiltshire / Hill).

Linearised in-plane motion of the vehicle relative to a station on a circular
orbit, in the station-centred frame:
  +x  radial, away from Earth (R-bar)
  +y  along-track, the direction of orbital motion (V-bar)

  x'' = 3 n^2 x + 2 n y'  + a_x
  y'' =        - 2 n x'   + a_y

where n = 2 pi / orbit period is the mean motion and a is applied
acceleration (thrust, impacts). Out-of-plane motion is not modelled (2D).

The orbit is public knowledge about the station, so both the simulator and
the controller use these functions.
"""

import math


def mean_motion(period_s):
    return 2.0 * math.pi / period_s


def natural_accel(n, x, y, vx, vy):
    """Acceleration with no thrust, in the station frame (m/s^2)."""
    return 3.0 * n * n * x + 2.0 * n * vy, -2.0 * n * vx


def free_drift(n, x0, y0, vx0, vy0, t):
    """Analytic CW solution with no applied acceleration: (x, y, vx, vy) at t."""
    s, c = math.sin(n * t), math.cos(n * t)
    x = (4 - 3 * c) * x0 + s / n * vx0 + 2 / n * (1 - c) * vy0
    y = 6 * (s - n * t) * x0 + y0 - 2 / n * (1 - c) * vx0 + (4 * s - 3 * n * t) / n * vy0
    vx = 3 * n * s * x0 + c * vx0 + 2 * s * vy0
    vy = -6 * n * (1 - c) * x0 - 2 * s * vx0 + (4 * c - 3) * vy0
    return x, y, vx, vy
