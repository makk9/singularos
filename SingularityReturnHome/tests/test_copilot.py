"""AI copilot: plan validation, execution under authority, fallback.

Uses ScriptedCopilot (no model server). The plans are the examples in
intelligence/examples/, i.e. what a correct copilot would propose.
"""

import json
from pathlib import Path

import pytest

from intelligence.copilot import ScriptedCopilot, context_text
from singularos_sim.config import controller_spec, load_config
from singularos_sim.plan_validator import validate_plan
from singularos_sim.runner import run_scenario

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "scenarios"
EXAMPLES = ROOT / "intelligence" / "examples"


def plans(name):
    return json.loads((EXAMPLES / f"{name}.json").read_text())


def run(scenario, copilot, tmp_path):
    return run_scenario(load_config(SCENARIOS / f"{scenario}.toml"), tmp_path, copilot=copilot)


def events(summary, kind):
    return [e for e in summary["copilot"] if e["type"] == kind]


@pytest.fixture(scope="module")
def vctx():
    config = load_config(SCENARIOS / "copilot_coast_in.toml")
    r = config["recovery"]
    return {
        "position_m": (8.0, 0.0), "speed_m_s": 0.0, "distance_to_dock_m": 8.0,
        "predock_m": (r["predock_distance_m"], 0.0), "staging_m": (8.0, 0.0), "return_points_m": [],
        "usable": {"forward", "left", "right"},
        "health": {"forward": 1.0, "backward": 0.0, "left": 1.0, "right": 1.0},
        "degraded": True, "recovery": r, "docking": config["docking"], "constraints": [],
        "station": config["station"]["components"], "spec": controller_spec(config), "mass_kg": 51.5, "fuel_kg": 1.5,
    }


def step_plan(decision, *steps):
    return {"schema_version": 1, "assessment": "test", "decision": decision, "steps": list(steps),
            "advisories_considered": [], "rationale": "test"}


def test_validator_accepts_coast_in_and_rejects_powered_approach_without_backward(vctx):
    assert validate_plan(plans("coast_in")[0], vctx)["accepted"]
    v = validate_plan(step_plan("DOCK", {"action": "PREDOCK_STOP"}, {"action": "FINAL_APPROACH"}), vctx)
    assert not v["accepted"] and v["checks"]["capability"] != "pass"


def test_validator_structure_prerequisites_speed_and_clearance(vctx):
    v = validate_plan(step_plan("DOCK", {"action": "COAST_IN", "speed_m_s": 0.03}), vctx)
    assert v["checks"]["prerequisites"] != "pass"
    v = validate_plan(step_plan("DOCK", {"action": "PREDOCK_STOP"}, {"action": "COAST_IN", "speed_m_s": 0.09}), vctx)
    assert v["checks"]["speed_limits"] != "pass"
    v = validate_plan(step_plan("HOLD", {"action": "GOTO", "x_m": -8.0, "y_m": 0.0}, {"action": "HOLD_AT", "x_m": -8.0, "y_m": 0.0}), vctx)
    assert v["checks"]["clearance"] != "pass"  # straight through the core module
    v = validate_plan(step_plan("HOLD", {"action": "PREDOCK_STOP"}), vctx)
    assert v["checks"]["structure"] != "pass"


def test_validator_enforces_advisories(vctx):
    closed = {**vctx, "constraints": [{"type": "dock_closed", "advisory": "A1"}]}
    assert validate_plan(plans("coast_in")[0], closed)["checks"]["advisories"] != "pass"
    slow = {**vctx, "constraints": [{"type": "max_approach_speed", "value_m_s": 0.02, "within_m": 3.0, "advisory": "A2"}]}
    v = validate_plan(plans("coast_in")[0], slow)  # coast 0.03 and default pre-dock speed exceed the limit
    assert any("exceeds advisory" in p for p in v["problems"]) and any("PREDOCK_STOP" in p for p in v["problems"])


def test_copilot_coast_in_docks_where_baseline_holds(tmp_path):
    baseline = run("copilot_coast_in", None, tmp_path / "b")
    assert baseline["outcome"] == "HOLD"
    s = run("copilot_coast_in", ScriptedCopilot(plans("coast_in")), tmp_path / "c")
    assert s["outcome"] == "DOCKED" and s["truth_docking_check"]["pass"] and s["collision"] is None
    assert s["authority"] == "copilot" and events(s, "copilot_verdict")[0]["accepted"]


def test_copilot_fixes_rejected_plan_and_respects_speed_advisory(tmp_path):
    baseline = run("copilot_advisory_speed", None, tmp_path / "b")
    assert baseline["advisory_violations"]  # the baseline ignores the advisory
    s = run("copilot_advisory_speed", ScriptedCopilot(plans("advisory_speed")), tmp_path / "c")
    verdicts = events(s, "copilot_verdict")
    assert [v["accepted"] for v in verdicts] == [False, True]
    assert s["outcome"] == "DOCKED" and not s["advisory_violations"] and s["collision"] is None


def test_copilot_holds_when_dock_closed(tmp_path):
    baseline = run("copilot_trap_dock_closed", None, tmp_path / "b")
    assert baseline["outcome"] == "DOCKED" and baseline["advisory_violations"]
    s = run("copilot_trap_dock_closed", ScriptedCopilot(plans("dock_closed")), tmp_path / "c")
    assert s["outcome"] == "HOLD" and not s["advisory_violations"] and s["hold_max_deviation_m"] < 1.0


def test_rejected_plans_fall_back_to_baseline(tmp_path):
    bad = step_plan("DOCK", {"action": "PREDOCK_STOP"}, {"action": "FINAL_APPROACH"})  # needs backward
    s = run("copilot_coast_in", ScriptedCopilot([bad]), tmp_path)
    assert [v["accepted"] for v in events(s, "copilot_verdict")] == [False, False, False]
    assert s["authority"] == "baseline" and s["outcome"] == "HOLD"


def test_copilot_error_falls_back_to_baseline(tmp_path):
    class Broken:
        name = "broken"

        def propose(self, ctx, history=()):
            raise RuntimeError("model server down")

    s = run("copilot_coast_in", Broken(), tmp_path)
    assert events(s, "copilot_error") and s["authority"] == "baseline" and s["outcome"] == "HOLD"


@pytest.mark.parametrize("fmt", ["report", "summary"])
def test_copilot_prompt_has_evidence_but_not_baseline_decision_or_truth(tmp_path, fmt):
    agent = ScriptedCopilot(plans("dock_closed"), input_format=fmt)
    run("copilot_trap_dock_closed", agent, tmp_path)
    text = agent.calls[0]["context"]
    assert "STA-11" in text and "docking port A is CLOSED" in text
    if fmt == "report":
        assert text.splitlines()[1].startswith("KEY FACTS: failed thrusters: left")
        report = json.loads(next(line for line in text.splitlines() if line.startswith("{")))
        assert "UNAVAILABLE STEPS: " in text and "closes the dock" in text
        assert report["thrusters"]["left"]["status"] == "FAILED"
        assert {d["thruster"] for d in report["diagnostics"]} >= {"left", "forward", "backward", "right"}
        assert report["alerts"][0]["code"] == "PROPULSION_ANOMALY"
    else:
        assert "left FAILED" in text
    for leak in ("Deterministic decision", "RETURN;", "baseline", "thruster_health", "effectiveness", "truth", "impact"):
        assert leak not in text


def test_failed_copilot_under_advisories_falls_back_to_hold(tmp_path):
    # Rejected plans while a dock-closed advisory is active: the baseline would
    # dock into the closed port, so the fallback holds instead.
    bad = step_plan("HOLD", {"action": "GOTO", "x_m": 8.0, "y_m": 0.0}, {"action": "HOLD_AT", "x_m": 8.0, "y_m": 0.0})
    s = run("copilot_trap_dock_closed", ScriptedCopilot([bad]), tmp_path)
    assert s["authority"] == "baseline" and s["outcome"] == "HOLD" and not s["advisory_violations"]


def test_validator_checks_goto_speed_inside_advisory_zone(vctx):
    slow = {**vctx, "constraints": [{"type": "max_approach_speed", "value_m_s": 0.02, "within_m": 3.0, "advisory": "A2"}]}
    plan = step_plan("DOCK", {"action": "RETURN_TO_STAGING"}, {"action": "GOTO", "x_m": 2.0, "y_m": 0.0},
                     {"action": "PREDOCK_STOP", "speed_m_s": 0.02}, {"action": "COAST_IN", "speed_m_s": 0.02})
    v = validate_plan(plan, slow)
    assert any("GOTO" in p and "speed-limit zone" in p for p in v["problems"])


def test_planning_facts_flag_blocked_route_unavailable_steps_and_speed_cap(vctx):
    from singularos_sim.anomaly_report import key_facts
    from singularos_sim.plan_validator import planning_facts
    # Behind the north solar array, as after the thruster_fault impact: the
    # straight line to staging is the GOTO the validator would reject.
    behind = {**vctx, "position_m": (-10.0, 18.0),
              "constraints": [{"type": "max_approach_speed", "value_m_s": 0.02, "within_m": 3.0, "advisory": "A2"}]}
    facts = planning_facts(behind)
    assert facts["straight_line_to_staging"]["blocked_by"] == "North solar array"
    goto = step_plan("HOLD", {"action": "HOLD_AT", "x_m": 8.0, "y_m": 0.0})
    assert validate_plan(goto, behind)["checks"]["clearance"] != "pass"
    assert "FINAL_APPROACH" in facts["unavailable_steps"] and "COAST_IN" in facts["available_steps"]
    assert facts["approach_speed_cap"]["max_m_s"] == 0.02
    text = key_facts({"thrusters": {n: {"status": "FAILED" if n == "backward" else "NOMINAL", "health_pct": 0}
                                    for n in ("forward", "backward", "left", "right")},
                      "nav": {"speed_m_s": 0.0}, "proximity": {"dock_range_m": 20.6}, "station_messages": [],
                      "planning": facts})
    assert "BLOCKED by North solar array" in text and "SPEED CAP: 0.020" in text and "UNAVAILABLE STEPS: " in text
    # From staging itself the line is clear, and the validator agrees.
    assert planning_facts(vctx)["straight_line_to_staging"]["clear"]
    assert validate_plan(goto, vctx)["checks"]["clearance"] == "pass"


def test_planning_facts_dock_closed_and_no_pair(vctx):
    from singularos_sim.plan_validator import planning_facts
    closed = planning_facts({**vctx, "constraints": [{"type": "dock_closed", "advisory": "A1"}]})
    assert {"COAST_IN", "FINAL_APPROACH"} <= set(closed["unavailable_steps"]) and closed["dock_closed_by"] == ["A1"]
    lone = planning_facts({**vctx, "usable": {"forward"}})
    assert lone["available_steps"] == ["SAFE_STOP"]


def test_copilot_report_carries_planning_facts(tmp_path):
    copilot = ScriptedCopilot(plans("advisory_speed"))
    run("copilot_advisory_speed", copilot, tmp_path)
    prompt = copilot.calls[0]["context"]
    assert "ROUTE: " in prompt and "AVAILABLE STEPS: " in prompt and "SPEED CAP: 0.020" in prompt


def test_retry_feedback_keeps_decision_unless_the_decision_is_at_fault():
    from intelligence.copilot import CopilotAgent

    class Client:
        class config:
            model = "fake"

        def chat(self, messages, schema):
            self.messages = messages
            return json.dumps(step_plan("HOLD", {"action": "RETURN_TO_STAGING"}, {"action": "HOLD_AT", "x_m": 8.0, "y_m": 0.0}))

    client = Client()
    agent = CopilotAgent(client)
    agent.input_format = "summary"
    rejected = step_plan("HOLD", {"action": "HOLD_AT", "x_m": 8.0, "y_m": 0.0})
    ctx = {"t": 1.0, "observed": {"x_m": 0, "y_m": 0, "vx_m_s": 0, "vy_m_s": 0, "fuel_kg": 1}, "distance_to_dock_m": 1,
           "health_estimate": {"forward": 1.0}, "usable": ["forward"], "fuel_reserve_kg": 0.1, "advisories": []}
    agent.propose(ctx, [(rejected, ["path to HOLD_AT (8.0, 0.0) passes 0.0 m from North solar array"])])
    assert "keep decision HOLD" in client.messages[-1]["content"]
    agent.propose(ctx, [(rejected, ["advisory A1 closes the dock: docking not allowed"])])
    assert "keep decision" not in client.messages[-1]["content"]


def test_plan_schema_allows_only_each_actions_own_parameters():
    from intelligence.copilot import load_schema
    from intelligence.harness import schema_problems
    schema = load_schema()
    for name in ("coast_in", "advisory_speed", "dock_closed"):
        for plan in plans(name):
            assert schema_problems(plan, schema) == [], name
    # The shape seen in live runs: coordinates on PREDOCK_STOP instead of a speed.
    bad = step_plan("DOCK", {"action": "RETURN_TO_STAGING"}, {"action": "PREDOCK_STOP", "x_m": 0.8, "y_m": 0.0},
                    {"action": "FINAL_APPROACH", "speed_m_s": 0.02})
    problems = schema_problems(bad, schema)
    assert "proposal.steps[1].speed_m_s is required" in problems and "proposal.steps[1].x_m is not allowed" in problems


def test_validator_range_checks_predock_speed(vctx):
    v = validate_plan(step_plan("DOCK", {"action": "PREDOCK_STOP", "speed_m_s": 0.0}, {"action": "COAST_IN", "speed_m_s": 0.02}), vctx)
    assert any("PREDOCK_STOP speed 0.000" in p for p in v["checks"]["speed_limits"])


def test_planning_facts_docking_line(vctx):
    from singularos_sim.plan_validator import planning_facts
    lost_backward = planning_facts(vctx)["docking"]
    assert lost_backward == {"possible": True, "via": ["COAST_IN"], "preferred": "COAST_IN"}
    intact = planning_facts({**vctx, "usable": {"forward", "backward", "right"}})["docking"]
    assert intact["preferred"] == "FINAL_APPROACH" and intact["via"] == ["FINAL_APPROACH", "COAST_IN"]
    closed = planning_facts({**vctx, "constraints": [{"type": "dock_closed", "advisory": "A1"}]})["docking"]
    assert not closed["possible"]
