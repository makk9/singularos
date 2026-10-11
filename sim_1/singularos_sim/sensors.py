"""Sensors: turn truth into observations following the MISSION.md section 6 contract.

Every observation carries exactly: source, timestamp, available, value,
uncertainty. Uncertainty values are 1-sigma standard deviations in the same
units as the corresponding value fields.

Each sensor draws Gaussian noise from its own random stream, seeded from the
scenario seed and the sensor's source id, so adding a sensor does not change
the noise sequence of the others.

Readings that come from the same hardware are emitted as one observation
(navigation position and velocity together; attitude heading and rate
together) so that later faults affect them jointly.
"""

import random
from dataclasses import dataclass

from .config import steps_for
from .dynamics import wrap_angle


@dataclass(frozen=True)
class Observation:
    source: str
    timestamp: float
    available: bool
    value: dict | None
    uncertainty: dict | None

    def to_dict(self):
        return {
            "source": self.source,
            "timestamp": self.timestamp,
            "available": self.available,
            "value": None if self.value is None else dict(self.value),
            "uncertainty": None if self.uncertainty is None else dict(self.uncertainty),
        }


class Sensor:
    source = ""

    def __init__(self, params, dt, seed):
        self.params = params
        self.period_steps = steps_for(params["period_s"], dt, f"sensors {self.source} period_s")
        self.rng = random.Random(f"{seed}/{self.source}")

    def due(self, step):
        return step % self.period_steps == 0

    def measure(self, t, truth):
        raise NotImplementedError

    def noisy(self, value, std):
        return value + self.rng.gauss(0.0, std)


class AttitudeSensor(Sensor):
    source = "attitude_sensor"

    def measure(self, t, truth):
        p = self.params
        return Observation(
            source=self.source,
            timestamp=t,
            available=True,
            value={
                "heading_rad": wrap_angle(self.noisy(truth.heading_rad, p["heading_std_rad"])),
                "angular_rate_rad_s": self.noisy(truth.angular_rate_rad_s, p["angular_rate_std_rad_s"]),
            },
            uncertainty={
                "heading_rad": p["heading_std_rad"],
                "angular_rate_rad_s": p["angular_rate_std_rad_s"],
            },
        )


class NavigationSensor(Sensor):
    """Station-relative navigation: full position and velocity fix."""

    source = "navigation"

    def measure(self, t, truth):
        p = self.params
        ps, vs = p["position_std_m"], p["velocity_std_m_s"]
        return Observation(
            source=self.source,
            timestamp=t,
            available=True,
            value={
                "x_m": self.noisy(truth.x_m, ps),
                "y_m": self.noisy(truth.y_m, ps),
                "vx_m_s": self.noisy(truth.vx_m_s, vs),
                "vy_m_s": self.noisy(truth.vy_m_s, vs),
            },
            uncertainty={"x_m": ps, "y_m": ps, "vx_m_s": vs, "vy_m_s": vs},
        )


class FuelMonitor(Sensor):
    source = "fuel_monitor"

    def measure(self, t, truth):
        std = self.params["fuel_std_kg"]
        return Observation(
            source=self.source,
            timestamp=t,
            available=True,
            value={"fuel_kg": max(0.0, self.noisy(truth.fuel_kg, std))},
            uncertainty={"fuel_kg": std},
        )


SENSOR_TYPES = {"attitude": AttitudeSensor, "navigation": NavigationSensor, "fuel": FuelMonitor}


def build_sensors(config):
    dt = config["scenario"]["sim_dt_s"]
    seed = config["scenario"]["seed"]
    return [SENSOR_TYPES[name](params, dt, seed) for name, params in config["sensors"].items()]
