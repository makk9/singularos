"""Run a scenario: step truth at a fixed timestep, sample sensors, tick the
controller at its slower cadence, and write a per-step log.

Per step k (t = k * sim_dt_s):
  1. Sensors that are due sample the truth at t.
  2. If the controller is due, it receives the observations emitted since its
     last tick and returns a command, which is held until its next tick.
  3. One log line is written: truth and observations under separate keys.
  4. If the controller has declared DOCKED, the run ends. Otherwise truth is
     advanced one step with the held command.

Station clearance (truth vehicle disc vs. station components, docking port
excluded) is computed every step for evaluation and logged under truth. A
negative clearance is a collision; the run continues so the log shows what
happened, but the outcome records it.

Truth fault events (impact, thruster fault) are logged under truth.events.
Controller events (anomaly, diagnostics, plan) are logged under
controller.events. The run ends when the controller reaches a final outcome
(DOCKED, HOLD, ABORT) or max_duration_s (NOT_DOCKED). After HOLD or ABORT the
run continues for scenario.post_outcome_observe_s (HOLD keeps station-keeping,
ABORT drifts unpowered) so the log shows what that outcome leads to.

Output directory contents:
  config.json  - resolved scenario config including the seed used
  log.jsonl    - one JSON object per sim step
  summary.json - outcome and end-of-run metrics
"""

import json
import math
from pathlib import Path

from .config import controller_spec, steps_for
from .controller import Controller
from .dynamics import Command, Vehicle, wrap_angle
from .sensors import build_sensors
from .station import Station

DEFAULT_RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


def truth_docking_check(state, config):
    """Grade the final truth state against the same thresholds. Evaluation only;
    never visible to the controller."""
    d = config["docking"]
    distance = math.hypot(state.x_m, state.y_m)
    speed = math.hypot(state.vx_m_s, state.vy_m_s)
    alignment = abs(wrap_angle(config["mission"]["dock_heading_rad"] - state.heading_rad))
    return {
        "pass": distance <= d["max_distance_m"]
        and speed <= d["max_relative_speed_m_s"]
        and alignment <= d["max_alignment_error_rad"],
        "distance_m": distance,
        "relative_speed_m_s": speed,
        "alignment_error_rad": alignment,
    }


def run_scenario(config, out_dir=None):
    scenario = config["scenario"]
    dt = scenario["sim_dt_s"]
    ctrl_steps = steps_for(scenario["controller_period_s"], dt, "controller_period_s")
    max_steps = int(round(scenario["max_duration_s"] / dt))

    if out_dir is None:
        out_dir = DEFAULT_RUNS_DIR / f"{scenario['name']}-seed{scenario['seed']}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n")

    vehicle = Vehicle(config)
    sensors = build_sensors(config)
    controller = Controller(
        controller_spec(config), config["mission"], config["controller"], config["docking"], config["recovery"]
    )
    station = Station(config)
    initial_fuel = vehicle.state.fuel_kg
    # Minimum clearance in flight, excluding departure, the pre-dock stop and
    # final approach, which are necessarily close to the station:
    # (clearance, component, t).
    min_clearance = (float("inf"), None, None)
    first_collision = None
    truth_events, controller_events = [], []

    observe_steps = int(round(scenario["post_outcome_observe_s"] / dt))
    outcome_step = None
    hold_deviation = 0.0
    command = Command.idle()
    pending = []
    step = 0
    with open(out_dir / "log.jsonl", "w") as log:
        while True:
            t = step * dt
            emitted = [s.measure(t, vehicle.state) for s in sensors if s.due(step)]
            pending.extend(emitted)

            clearance, nearest = station.clearance(vehicle.state.x_m, vehicle.state.y_m)
            near_dock = controller.phase in ("DEPART", "APPROACH", "DOCKED") or controller.leg_name == "pre-dock"
            if not near_dock and clearance < min_clearance[0]:
                min_clearance = (clearance, nearest, t)
            if clearance < 0 and first_collision is None:
                first_collision = {"t": t, "component": nearest}
            record = {
                "step": step,
                "t": t,
                "truth": {
                    **vehicle.state.to_dict(),
                    "thrust_n": dict(vehicle.last_thrust_n),
                    "station_clearance_m": clearance,
                    "nearest_component": nearest,
                    "thruster_health": dict(vehicle.effectiveness),
                },
                "observations": [o.to_dict() for o in emitted],
            }
            events = vehicle.take_events()
            if events:
                record["truth"]["events"] = events
                truth_events.extend(events)
            if step % ctrl_steps == 0:
                command = controller.update(t, pending)
                pending = []
                record["controller"] = {
                    "phase": controller.phase,
                    "leg": controller.leg_name,
                    "command": command.to_dict(),
                    "docking_check": controller.last_docking_check,
                    "health_estimate": dict(controller.health),
                    "health_verified": dict(controller.health_verified),
                    "monitor_residual_m_s": controller.last_residual,
                }
                events = controller.take_events()
                if events:
                    record["controller"]["events"] = events
                    controller_events.extend(events)
            log.write(json.dumps(record) + "\n")

            if controller.finished and outcome_step is None:
                outcome_step = step
            if outcome_step is not None and controller.final == "HOLD":
                hp = controller.legs[controller.leg_index].target
                hold_deviation = max(hold_deviation, math.hypot(vehicle.state.x_m - hp[0], vehicle.state.y_m - hp[1]))
            if outcome_step is not None and (
                controller.final == "DOCKED" or step - outcome_step >= observe_steps
            ):
                break
            if step >= max_steps:
                break
            vehicle.step(command)
            step += 1

    final = vehicle.state
    outcome = controller.final or "NOT_DOCKED"
    reasons = {
        "DOCKED": "docking criteria met",
        "HOLD": "fallback: holding at a safe point",
        "ABORT": "fallback: abort, thrusters off",
        "NOT_DOCKED": "max_duration_s reached",
    }
    impact = next((e for e in truth_events if e["type"] == "impact"), None)
    anomaly = next((e for e in controller_events if e["type"] == "anomaly_detected"), None)
    summary = {
        "scenario": scenario["name"],
        "seed": scenario["seed"],
        "outcome": outcome,
        "expected_outcome": scenario["expected_outcome"],
        "reason": reasons[outcome],
        "final_phase": controller.phase,
        "sim_time_s": step * dt,
        "steps": step,
        "fuel_used_kg": initial_fuel - final.fuel_kg,
        "fuel_remaining_kg": final.fuel_kg,
        "controller_docking_check": controller.last_docking_check,
        "truth_docking_check": truth_docking_check(final, config),
        "collision": first_collision,
        "min_clearance_in_flight": {"clearance_m": min_clearance[0], "component": min_clearance[1], "t": min_clearance[2]},
        "inspections_completed": controller.inspections_completed(),
        "faults_injected": config["faults"],
        "anomaly_detected_t": anomaly["t"] if anomaly else None,
        "detection_latency_s": anomaly["t"] - impact["t"] if anomaly and impact else None,
        "investigations": controller.investigations,
        "outcome_t": None if outcome_step is None else outcome_step * dt,
        "post_outcome_observed_s": 0.0 if outcome_step is None else (step - outcome_step) * dt,
        # Truth: farthest the vehicle got from the hold point while holding.
        "hold_max_deviation_m": hold_deviation if controller.final == "HOLD" else None,
        "final_position_m": [final.x_m, final.y_m],
        "plan": next((e for e in reversed(controller_events) if e["type"] == "plan"), None),
        # Evaluation only: compare the controller's estimates with truth.
        "health_estimate_vs_truth": {
            name: {"estimate": controller.health[name], "truth": vehicle.effectiveness[name]}
            for name in vehicle.effectiveness
        },
        "out_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
