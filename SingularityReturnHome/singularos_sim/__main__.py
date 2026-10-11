"""CLI: python -m singularos_sim [scenario.toml] [--seed N] [--out DIR]
        python -m singularos_sim --all [--seed N]"""

import argparse
import sys
from pathlib import Path

from .config import default_scenario_path, load_config, with_seed
from .replay import build_replay, describe_faults
from .runner import run_scenario


def run_all(seed):
    """Run every scenario in the scenarios directory with one seed and link the
    replays with a scenario picker. Returns the process exit code."""
    scenario_dir = default_scenario_path().parent
    runs = []
    for path in sorted(scenario_dir.glob("*.toml")):
        try:
            config = with_seed(load_config(path), seed)
        except (KeyError, ValueError) as exc:
            print(f"skipped {path.name}: not a valid scenario ({exc!r})")
            continue
        runs.append(run_scenario(config))
    # Nominal first, then the rest by name.
    runs.sort(key=lambda s: (s["scenario"] != "nominal", s["scenario"]))
    entries = []
    for s in runs:
        ok = s["outcome"] == s["expected_outcome"] and s["collision"] is None and (
            s["outcome"] != "DOCKED" or s["truth_docking_check"]["pass"])
        s["ok"] = ok
        entries.append({
            "name": s["scenario"],
            "href": f"../{Path(s['out_dir']).name}/replay.html",
            "label": f"{s['scenario']} \u2014 {describe_faults(s['faults_injected'])} \u2014 {s['outcome']}"
                     + ("" if ok else " (FAIL)"),
        })
    print(f"{'scenario':<28} {'faults':<26} {'outcome':<11} {'expected':<11} result")
    for s in runs:
        build_replay(s["out_dir"], entries)
        print(f"{s['scenario']:<28} {describe_faults(s['faults_injected']):<26} {s['outcome']:<11} "
              f"{s['expected_outcome']:<11} {'PASS' if s['ok'] else 'FAIL'}")
    if runs:
        print(f"replay (pick any scenario from the header): {Path(runs[0]['out_dir']) / 'replay.html'}")
    return 0 if runs and all(s["ok"] for s in runs) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="singularos_sim", description="Run a Singularity Return Home simulator scenario.")
    parser.add_argument("scenario", nargs="?", default=str(default_scenario_path()), help="scenario TOML file")
    parser.add_argument("--seed", type=int, default=None, help="override the scenario seed")
    parser.add_argument("--out", default=None, help="output directory (default: runs/<name>-seed<seed>)")
    parser.add_argument("--all", action="store_true",
                        help="run every scenario in scenarios/ and link the replays with a scenario picker")
    args = parser.parse_args(argv)

    if args.all:
        return run_all(args.seed)

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
