"""Static station geometry and truth-side clearance checks.

Components are axis-aligned rectangles in the station frame. The vehicle is
treated as a disc of radius vehicle.radius_m. Clearance is the gap between the
vehicle disc and the nearest component (negative means overlap). The docking
port is excluded, since contact with it is the goal of docking.

These checks run on truth for evaluation only; the controller never sees them.
"""

import math


def distance_to_rect(x, y, lo, hi):
    """Distance from a point to a rectangle; 0 if the point is inside."""
    dx = max(lo[0] - x, 0.0, x - hi[0])
    dy = max(lo[1] - y, 0.0, y - hi[1])
    return math.hypot(dx, dy)


class Station:
    def __init__(self, config):
        self.components = config["station"]["components"]
        self.radius = config["vehicle"]["radius_m"]
        self.obstacles = [c for c in self.components if c["type"] != "docking_port"]

    def clearance(self, x, y):
        """Return (clearance_m, nearest component name)."""
        best, name = math.inf, None
        for c in self.obstacles:
            d = distance_to_rect(x, y, c["min_m"], c["max_m"]) - self.radius
            if d < best:
                best, name = d, c["name"]
        return best, name
