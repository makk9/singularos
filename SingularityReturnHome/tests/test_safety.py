import unittest
from math import sqrt

from simulation.orbit import MU, EARTH_RADIUS
from guidance.recovery import plan_recovery
from safety.validator import validate, validate_independently

class RecoverySafetyTests(unittest.TestCase):
    def setUp(self):
        r = EARTH_RADIUS + 400
        self.position = (r, 0, 0)
        self.velocity = (0, sqrt(MU / r) - 0.15, 0)

    def test_valid_recovery(self):
        plan = plan_recovery(self.position, self.velocity)
        result = validate_independently(self.position, self.velocity, plan)
        self.assertTrue(result["authorized"])

    def test_insufficient_fuel(self):
        plan = {
            "status": "PROPOSED",
            "delta_v_m_s": 130,
            "predicted_orbit": {"perigee_km": 200},
        }
        self.assertIn("INSUFFICIENT_FUEL", validate(plan)["reasons"])

    def test_falsified_trajectory(self):
        plan = {
            "status": "PROPOSED",
            "delta_v_m_s": 10,
            "predicted_orbit": {"perigee_km": 400},
        }
        result = validate_independently(self.position, self.velocity, plan)
        self.assertFalse(result["authorized"])
        self.assertIn("VERIFIED_PERIGEE_UNSAFE", result["reasons"])

if __name__ == "__main__":
    unittest.main()

class SevereEmergencyTests(unittest.TestCase):
    def test_recovery_exceeds_fuel_budget(self):
        r = EARTH_RADIUS + 400
        position = (r, 0, 0)
        velocity = (0, sqrt(MU / r) - 0.30, 0)

        plan = plan_recovery(position, velocity)
        result = validate_independently(position, velocity, plan)

        self.assertFalse(result["authorized"])
        self.assertIn("INSUFFICIENT_FUEL", result["reasons"])
        self.assertIn("MANEUVER_LIMIT_EXCEEDED", result["reasons"])
