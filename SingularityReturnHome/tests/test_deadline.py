import unittest
from math import sqrt

from navigation.deadline import time_to_altitude
from simulation.orbit import MU, EARTH_RADIUS


class EmergencyDeadlineTests(unittest.TestCase):
    def test_severe_emergency_countdown(self):
        r = EARTH_RADIUS + 400
        v = sqrt(MU / r) - 0.30

        seconds = time_to_altitude((r, 0, 0), (0, v, 0))

        self.assertIsNotNone(seconds)
        self.assertAlmostEqual(seconds / 60, 15.91, delta=0.02)

    def test_no_atmospheric_crossing(self):
        r = EARTH_RADIUS + 400
        v = sqrt(MU / r)

        seconds = time_to_altitude((r, 0, 0), (0, v, 0))

        self.assertIsNone(seconds)


if __name__ == "__main__":
    unittest.main()
