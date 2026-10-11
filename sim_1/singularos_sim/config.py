"""Scenario configuration loading.

A run is fully defined by a scenario TOML file plus a seed. The seed in the
file is the default; a caller may override it.

A scenario may start with `extends = "other.toml"` (path relative to the
file). The base is loaded first and the scenario's tables are merged over it:
tables merge key by key, every other value (including arrays and arrays of
tables) replaces the base value.
"""

import copy
import tomllib
from pathlib import Path

THRUSTER_NAMES = ("forward", "backward", "left", "right")
OUTCOMES = ("DOCKED", "HOLD", "ABORT", "NOT_DOCKED")

# Body-frame unit force direction of each thruster (body +x = nose, +y = left).
THRUSTER_DIRECTIONS = {
    "forward": (1.0, 0.0),
    "backward": (-1.0, 0.0),
    "left": (0.0, 1.0),
    "right": (0.0, -1.0),
}


def _merge(base, override):
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _load_raw(path, seen=()):
    path = Path(path).resolve()
    if path in seen:
        raise ValueError(f"circular extends at {path}")
    with open(path, "rb") as f:
        config = tomllib.load(f)
    base = config.pop("extends", None)
    if base is not None:
        config = _merge(_load_raw(path.parent / base, seen + (path,)), config)
    return config


def load_config(path):
    config = _load_raw(path)
    config.setdefault("faults", [])
    config["scenario"].setdefault("expected_outcome", "DOCKED")
    validate_config(config)
    return config


def steps_for(period_s, dt_s, what):
    """Convert a period to a whole number of sim steps, rejecting non-multiples."""
    steps = round(period_s / dt_s)
    if steps < 1 or abs(steps * dt_s - period_s) > 1e-9:
        raise ValueError(f"{what} ({period_s} s) must be a positive multiple of sim_dt_s ({dt_s} s)")
    return steps


def validate_config(config):
    scenario = config["scenario"]
    dt = scenario["sim_dt_s"]
    if dt <= 0:
        raise ValueError("sim_dt_s must be positive")
    steps_for(scenario["controller_period_s"], dt, "controller_period_s")
    for name, sensor in config["sensors"].items():
        steps_for(sensor["period_s"], dt, f"sensors.{name}.period_s")
    thrusters = config["vehicle"]["thrusters"]
    if set(thrusters) != set(THRUSTER_NAMES):
        raise ValueError(f"vehicle.thrusters must define exactly {THRUSTER_NAMES}")
    for name, t in thrusters.items():
        if t["max_thrust_n"] < 0 or t["fuel_rate_kg_s"] < 0 or t["response_delay_s"] < 0:
            raise ValueError(f"thruster {name}: values must be non-negative")
        if not 0.0 <= t["effectiveness"] <= 1.0:
            raise ValueError(f"thruster {name}: effectiveness must be in [0, 1]")
    for i, stop in enumerate(config["mission"]["route"]):
        if stop["kind"] not in ("inspect", "via"):
            raise ValueError(f"mission.route[{i}].kind must be 'inspect' or 'via'")
        if stop["kind"] == "inspect":
            for key in ("name", "target", "look_at_m", "hold_s"):
                if key not in stop:
                    raise ValueError(f"mission.route[{i}] (inspect) requires {key}")
            if stop["target"] not in {c["name"] for c in config["station"]["components"]}:
                raise ValueError(f"mission.route[{i}].target {stop['target']!r} is not a station component")
    for c in config["station"]["components"]:
        if not all(lo < hi for lo, hi in zip(c["min_m"], c["max_m"])):
            raise ValueError(f"station component {c['name']}: min_m must be below max_m")
    if config["scenario"]["expected_outcome"] not in OUTCOMES:
        raise ValueError(f"scenario.expected_outcome must be one of {OUTCOMES}")
    for i, fault in enumerate(config["faults"]):
        if fault["type"] == "impact":
            if fault["duration_s"] <= 0:
                raise ValueError(f"faults[{i}]: impact duration_s must be positive")
            steps_for(fault["duration_s"], dt, f"faults[{i}].duration_s")
        elif fault["type"] == "thruster":
            if fault["thruster"] not in THRUSTER_NAMES:
                raise ValueError(f"faults[{i}]: unknown thruster {fault['thruster']!r}")
            if not 0.0 <= fault["effectiveness"] <= 1.0:
                raise ValueError(f"faults[{i}]: effectiveness must be in [0, 1]")
        else:
            raise ValueError(f"faults[{i}]: unknown fault type {fault['type']!r}")
    if config["initial_state"]["fuel_kg"] < 0:
        raise ValueError("initial fuel must be non-negative")


def with_seed(config, seed):
    config = copy.deepcopy(config)
    if seed is not None:
        config["scenario"]["seed"] = int(seed)
    return config


def controller_spec(config):
    """The vehicle documentation the controller is allowed to know.

    Nominal design values only. True hardware health (thruster effectiveness),
    configured faults and initial truth state are deliberately excluded.
    """
    vehicle = config["vehicle"]
    return {
        "dry_mass_kg": vehicle["dry_mass_kg"],
        "max_rate_rad_s": vehicle["attitude"]["max_rate_rad_s"],
        "max_thrust_n": {name: vehicle["thrusters"][name]["max_thrust_n"] for name in THRUSTER_NAMES},
        "fuel_rate_kg_s": {name: vehicle["thrusters"][name]["fuel_rate_kg_s"] for name in THRUSTER_NAMES},
        "rotation_fuel_kg_per_rad_s": vehicle["attitude"]["fuel_per_rate_change_kg_per_rad_s"],
    }


def default_scenario_path():
    return Path(__file__).resolve().parent.parent / "scenarios" / "nominal.toml"
