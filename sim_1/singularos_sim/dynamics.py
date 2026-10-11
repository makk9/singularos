"""Hidden truth state and 2D rigid-body dynamics.

Frame: 2D, station-centred, dock at the origin. x/y in metres, heading in
radians measured counter-clockwise from +x. Body +x is the vehicle nose; body
+y is the vehicle's left side.

Orbital mechanics is deliberately omitted: there is no gravity, no orbital
relative motion (e.g. Clohessy-Wiltshire terms) and no drag. The only forces
are the vehicle's own thrusters. This is a 2D local-proximity model only.

Faults (config [[faults]]) act on truth only, through physics:
  impact   - an external world-frame acceleration and angular acceleration held
             for duration_s, delivering the configured delta-v and
             delta-omega. Position and heading stay continuous.
  thruster - from t_s, the named thruster's effectiveness becomes the given
             value. It still burns fuel at the commanded rate.
Fault onsets are reported as truth events; the controller never sees them.

Integrator: semi-implicit (symplectic) Euler at a fixed timestep. Velocity is
updated from the acceleration at the start of the step, then position from the
new velocity. Angular rate is updated before heading in the same way.
"""

import math
from collections import deque
from dataclasses import asdict, dataclass

from .config import THRUSTER_DIRECTIONS, THRUSTER_NAMES, steps_for


def wrap_angle(a):
    """Wrap an angle to [-pi, pi)."""
    return (a + math.pi) % (2.0 * math.pi) - math.pi


@dataclass
class TruthState:
    x_m: float
    y_m: float
    vx_m_s: float
    vy_m_s: float
    heading_rad: float
    angular_rate_rad_s: float
    fuel_kg: float

    def to_dict(self):
        return asdict(self)


@dataclass
class Command:
    """Actuator command. Throttles in [0, 1]; target angular rate in rad/s."""

    throttle: dict
    target_angular_rate_rad_s: float = 0.0

    @staticmethod
    def idle():
        return Command({name: 0.0 for name in THRUSTER_NAMES}, 0.0)

    def to_dict(self):
        return {"throttle": dict(self.throttle), "target_angular_rate_rad_s": self.target_angular_rate_rad_s}


class Vehicle:
    """Owns the truth state and advances it one fixed step at a time."""

    def __init__(self, config):
        dt = config["scenario"]["sim_dt_s"]
        init = config["initial_state"]
        vehicle = config["vehicle"]
        self.dt = dt
        self.dry_mass = vehicle["dry_mass_kg"]
        self.attitude = vehicle["attitude"]
        self.thrusters = vehicle["thrusters"]
        self.effectiveness = {name: self.thrusters[name]["effectiveness"] for name in THRUSTER_NAMES}
        self.faults = sorted(config.get("faults", []), key=lambda f: f["t_s"])
        self.step_count = 0
        self.events = []
        self.state = TruthState(
            x_m=init["x_m"],
            y_m=init["y_m"],
            vx_m_s=init["vx_m_s"],
            vy_m_s=init["vy_m_s"],
            heading_rad=wrap_angle(init["heading_rad"]),
            angular_rate_rad_s=init["angular_rate_rad_s"],
            fuel_kg=init["fuel_kg"],
        )
        # Response delay: a pure transport delay, rounded to whole sim steps.
        # Each thruster has a FIFO of pending throttle values.
        self._pipelines = {}
        for name in THRUSTER_NAMES:
            delay = self.thrusters[name]["response_delay_s"]
            n = 0 if delay == 0 else steps_for(delay, dt, f"thrusters.{name}.response_delay_s")
            self._pipelines[name] = deque([0.0] * n)
        self.last_thrust_n = {name: 0.0 for name in THRUSTER_NAMES}
        self.last_fuel_used_kg = 0.0

    def mass(self):
        return self.dry_mass + self.state.fuel_kg

    def _delayed_throttle(self, name, commanded):
        pipe = self._pipelines[name]
        pipe.append(min(max(commanded, 0.0), 1.0))
        return pipe.popleft()

    def _apply_faults(self):
        """Activate faults due at the current time; return the external
        (ax, ay, alpha) acting over this step."""
        t = self.step_count * self.dt
        ext_ax = ext_ay = ext_alpha = 0.0
        for fault in self.faults:
            start = int(round(fault["t_s"] / self.dt))
            if fault["type"] == "thruster" and self.step_count == start:
                self.effectiveness[fault["thruster"]] = fault["effectiveness"]
                self.events.append({"t": t, "type": "thruster_fault", "thruster": fault["thruster"],
                                    "effectiveness": fault["effectiveness"]})
            elif fault["type"] == "impact":
                n = int(round(fault["duration_s"] / self.dt))
                if start <= self.step_count < start + n:
                    dv = fault["delta_v_m_s"]
                    ext_ax += dv[0] / fault["duration_s"]
                    ext_ay += dv[1] / fault["duration_s"]
                    ext_alpha += fault.get("delta_omega_rad_s", 0.0) / fault["duration_s"]
                if self.step_count == start:
                    self.events.append({"t": t, "type": "impact", "x_m": self.state.x_m, "y_m": self.state.y_m,
                                        "delta_v_m_s": list(dv), "delta_omega_rad_s": fault.get("delta_omega_rad_s", 0.0)})
        return ext_ax, ext_ay, ext_alpha

    def take_events(self):
        events, self.events = self.events, []
        return events

    def step(self, command):
        s = self.state
        dt = self.dt
        fuel_start = s.fuel_kg
        ext_ax, ext_ay, ext_alpha = self._apply_faults()

        # Translational thrust. Effectiveness scales delivered force, not fuel
        # use: a degraded thruster still burns propellant at the commanded rate.
        throttles = {name: self._delayed_throttle(name, command.throttle.get(name, 0.0)) for name in THRUSTER_NAMES}
        demand = sum(throttles[n] * self.thrusters[n]["fuel_rate_kg_s"] * dt for n in THRUSTER_NAMES)
        scale = 1.0 if demand <= s.fuel_kg else (s.fuel_kg / demand if demand > 0 else 0.0)

        mass = self.mass()
        fx_body = fy_body = 0.0
        for name in THRUSTER_NAMES:
            t = self.thrusters[name]
            thrust = throttles[name] * scale * t["max_thrust_n"] * self.effectiveness[name]
            self.last_thrust_n[name] = thrust
            dx, dy = THRUSTER_DIRECTIONS[name]
            fx_body += thrust * dx
            fy_body += thrust * dy
        s.fuel_kg = max(0.0, s.fuel_kg - demand * scale)

        c, sn = math.cos(s.heading_rad), math.sin(s.heading_rad)
        ax = (c * fx_body - sn * fy_body) / mass + ext_ax
        ay = (sn * fx_body + c * fy_body) / mass + ext_ay

        s.vx_m_s += ax * dt
        s.vy_m_s += ay * dt
        s.x_m += s.vx_m_s * dt
        s.y_m += s.vy_m_s * dt

        # Attitude: slew angular rate toward the (rate-limited) target with
        # bounded angular acceleration. Changing angular rate costs fuel in
        # proportion to the magnitude of the change.
        att = self.attitude
        max_rate = att["max_rate_rad_s"]
        target = min(max(command.target_angular_rate_rad_s, -max_rate), max_rate)
        max_delta = att["max_angular_accel_rad_s2"] * dt
        delta = min(max(target - s.angular_rate_rad_s, -max_delta), max_delta)
        cost_per = att["fuel_per_rate_change_kg_per_rad_s"]
        if cost_per > 0 and abs(delta) * cost_per > s.fuel_kg:
            delta = math.copysign(s.fuel_kg / cost_per, delta)
        s.fuel_kg = max(0.0, s.fuel_kg - abs(delta) * cost_per)
        s.angular_rate_rad_s += delta + ext_alpha * dt
        s.heading_rad = wrap_angle(s.heading_rad + s.angular_rate_rad_s * dt)

        self.last_fuel_used_kg = fuel_start - s.fuel_kg
        self.step_count += 1
