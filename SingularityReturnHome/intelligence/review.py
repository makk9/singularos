"""Run an LLM proposal's requested checks against the numerical planner.

The context is built by the controller from controller-side information only
(observations, health estimates, planner results); see
singularos_sim.controller.Controller._advice_context. Each requested check
returns pass (True), fail (False) or not evaluated (None) with a detail line.
The proposal never changes what the controller does: the deterministic
decision keeps actuator authority (MISSION.md section 7).
"""

PAIRS = (("forward", "backward"), ("left", "right"))
DOCKING_MODES = ("RETURN", "APPROACH", "DOCKED")


def _fuel_budget(p, ctx):
    params = p.plan.get("parameters", {})
    dv = params.get("max_delta_v_mps")
    budget = ctx.get("available_delta_v_m_s")
    if dv is not None and budget is not None and dv > budget:
        return False, f"proposed {dv:.1f} m/s exceeds {budget:.1f} m/s available"
    if p.mode in DOCKING_MODES and ctx.get("return_fuel_ok") is False:
        return False, "return fuel x margin exceeds budget after reserve"
    if budget is None:
        return None, "delta-v budget not computed at this decision"
    return True, f"{budget:.1f} m/s available" + (f", proposed {dv:.1f} m/s" if dv is not None else "")


def _orbit_safety(p, ctx):
    orbit = ctx.get("orbit")
    if orbit is None:
        return None, "orbit not computed"
    safe = ctx["safe_perigee_km"]
    if orbit["perigee_km"] >= safe:
        return True, f"perigee {orbit['perigee_km']:.1f} km at or above {safe:.0f} km"
    action = p.plan["action"]
    if action == "BRAKE" and ctx.get("brake_feasible"):
        return True, "braking restores the station orbit and fits the budget"
    if action == "RAISE_PERIGEE" and ctx.get("safe_orbit_authorized"):
        return True, "perigee raise authorised by independent validation"
    return False, f"perigee {orbit['perigee_km']:.1f} km below {safe:.0f} km and {action} does not restore it within budget"


def _trajectory(p, ctx):
    action = p.plan["action"]
    if action == "RAISE_PERIGEE":
        ok = ctx.get("safe_orbit_authorized")
        return (None, "no perigee-raise plan at this decision") if ok is None else (
            ok, "independent validation " + ("authorised" if ok else "rejected") + " the perigee raise")
    if action == "BRAKE":
        ok = ctx.get("brake_feasible")
        return (None, "braking not assessed at this decision") if ok is None else (
            ok, "braking " + ("fits" if ok else "does not fit") + " the budget before reentry")
    if p.mode in DOCKING_MODES or action in ("BEGIN_APPROACH", "FINAL_APPROACH", "DOCK_SEQUENCE"):
        ok = ctx.get("dock_feasible")
        return (None, "docking feasibility not assessed") if ok is None else (
            ok, "return and docking " + ("feasible" if ok else "infeasible") + " per planner")
    return None, f"no trajectory to check for {action}"


def _actuators(p, ctx):
    usable = set(ctx.get("usable", []))
    action = p.plan["action"]
    if p.mode in DOCKING_MODES:
        ok = {"forward", "backward"} <= usable
        return ok, "axial pair " + ("usable" if ok else "not usable") + " for docking"
    if p.mode == "HOLD" and action == "HOLD_POSITION":
        ok = any(a in usable and b in usable for a, b in PAIRS)
        return ok, "opposing pair " + ("available" if ok else "unavailable") + " for station-keeping"
    if action in ("BRAKE", "RAISE_PERIGEE", "REORIENT", "SAFE_RETREAT"):
        return bool(usable), f"{len(usable)} usable thruster(s)"
    return True, f"usable: {', '.join(sorted(usable)) or 'none'}"


def _docking(name):
    def check(p, ctx):
        dock = ctx.get("docking_check")
        if not dock:
            return None, "evaluated only during final approach"
        key = "alignment_error_rad" if name == "DOCK_ALIGNMENT" else "fresh"
        return bool(dock.get("criteria_met") if name == "DOCK_ALIGNMENT" else dock.get("fresh")), f"{key}: {dock.get(key)}"
    return check


def _collision(p, ctx):
    return None, "not implemented: routes are pre-planned; clearance is measured only in evaluation"


CHECKS = {
    "FUEL_BUDGET": _fuel_budget,
    "ORBIT_SAFETY": _orbit_safety,
    "TRAJECTORY_FEASIBILITY": _trajectory,
    "ACTUATOR_EFFECTIVENESS": _actuators,
    "DOCK_ALIGNMENT": _docking("DOCK_ALIGNMENT"),
    "OBSERVATION_FRESHNESS": _docking("OBSERVATION_FRESHNESS"),
    "COLLISION_CHECK": _collision,
}


def review(proposal, ctx):
    checks = {}
    for name in proposal.requested_checks:
        result, detail = CHECKS[name](proposal, ctx)
        checks[name] = {"pass": result, "detail": detail}
    failed = [n for n, c in checks.items() if c["pass"] is False]
    return {
        "checks": checks,
        "failed": failed,
        "deterministic_mode": ctx["mode"],
        "agrees_with_deterministic": proposal.mode == ctx["mode"],
    }
