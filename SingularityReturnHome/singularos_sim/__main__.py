"""CLI: python -m singularos_sim [scenario.toml] [--seed N] [--out DIR]"""

import argparse
import sys

from .config import default_scenario_path, load_config, with_seed
from .replay import build_replay
from .runner import run_scenario


def main(argv=None):
    parser = argparse.ArgumentParser(prog="singularos_sim", description="Run a Singularity Return Home simulator scenario.")
    parser.add_argument("scenario", nargs="?", default=str(default_scenario_path()), help="scenario TOML file")
    parser.add_argument("--seed", type=int, default=None, help="override the scenario seed")
    parser.add_argument("--out", default=None, help="output directory (default: runs/<name>-seed<seed>)")
    args = parser.parse_args(argv)

    config = with_seed(load_config(args.scenario), args.seed)
    s = run_scenario(config, args.out)
    replay = build_replay(s["out_dir"])
    truth = s["truth_docking_check"]
    print(f"scenario: {s['scenario']}  seed: {s['seed']}")
    print(f"outcome: {s['outcome']} ({s['reason']})  expected: {s['expected_outcome']}")
    for fault in s["faults_injected"]:
        detail = (f"{fault['thruster']} thruster effectiveness -> {fault['effectiveness']}" if fault["type"] == "thruster"
                  else f"delta-v {fault['delta_v_m_s']} m/s, delta-omega {fault.get('delta_omega_rad_s', 0.0)} rad/s")
        print(f"fault injected at t={fault['t_s']:.1f} s: {fault['type']}, {detail}")
    if s["anomaly_detected_t"] is not None:
        latency = f" (latency {s['detection_latency_s']:.1f} s)" if s["detection_latency_s"] is not None else ""
        print(f"anomaly detected at t={s['anomaly_detected_t']:.1f} s{latency}")
        est = ", ".join(f"{k} {v['estimate']:.2f} (truth {v['truth']:.2f})" for k, v in s["health_estimate_vs_truth"].items())
        print(f"diagnosed thruster health: {est}")
    if s["post_outcome_observed_s"]:
        dev = s["hold_max_deviation_m"]
        print(f"after {s['outcome']}: observed {s['post_outcome_observed_s']:.0f} s more; "
              + (f"max distance from hold point {dev:.2f} m" if dev is not None else
                 f"final position ({s['final_position_m'][0]:.1f}, {s['final_position_m'][1]:.1f}) m"))
    triage = s["orbital_triage"]
    if triage:
        print(f"orbital triage: {triage['decision']}; " + "; ".join(triage["reasons"]))
    end = s["orbit_at_end"]
    print(f"vehicle orbit at end: altitude {end['altitude_km']:.1f} km, perigee {end['perigee_km']:.1f} km"
          + (f"  REENTRY at t={s['reentry']['t']:.0f} s" if s["reentry"] else ""))
    if s["plan"]:
        print(f"recovery decision: {s['plan']['decision']}; " + "; ".join(s["plan"]["reasons"]))
    print(f"sim time: {s['sim_time_s']:.2f} s  steps: {s['steps']}")
    print(f"fuel used: {s['fuel_used_kg']:.4f} kg  remaining: {s['fuel_remaining_kg']:.4f} kg")
    print(
        f"truth at end: distance {truth['distance_m']:.4f} m, speed {truth['relative_speed_m_s']:.4f} m/s, "
        f"alignment error {truth['alignment_error_rad']:.4f} rad, within thresholds: {truth['pass']}"
    )
    col = s["collision"]
    clr = s["min_clearance_in_flight"]
    print(f"inspections completed: {len(s['inspections_completed'])} ({', '.join(s['inspections_completed']) or 'none'})")
    print(
        f"station collision: {'YES at t=%.1f s with %s' % (col['t'], col['component']) if col else 'none'}  "
        f"min clearance in flight: {clr['clearance_m']:.2f} m ({clr['component']})"
    )
    print(f"log: {s['out_dir']}")
    print(f"replay: {replay}")
    ok = s["outcome"] == s["expected_outcome"] and col is None
    if s["outcome"] == "DOCKED":
        ok = ok and truth["pass"]
    checks = [f"outcome {'matches' if s['outcome'] == s['expected_outcome'] else 'differs from'} expected",
              "no collision" if col is None else "collision"]
    if s["outcome"] == "DOCKED":
        checks.append("truth within docking thresholds" if truth["pass"] else "truth OUTSIDE docking thresholds")
    print(f"result: {'PASS' if ok else 'FAIL'} ({', '.join(checks)})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
