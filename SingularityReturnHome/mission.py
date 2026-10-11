from math import sqrt

from simulation.orbit import MU, EARTH_RADIUS, orbital_status
from safety.emergency import assess
from guidance.recovery import plan_recovery
from safety.validator import validate_independently
from control.execute import execute
from navigation.deadline import time_to_altitude

r = EARTH_RADIUS + 400
position = (r, 0, 0)
velocity = (0, sqrt(MU / r) - 0.15, 0)

print("SINGULARITY RETURN HOME")
print("INITIAL:", orbital_status(position, velocity))

emergency = assess(position, velocity, communications=False)
print("DETECTION:", emergency["hazards"])

deadline = time_to_altitude(position, velocity)
print("TIME TO 120 KM:", f"{deadline / 60:.2f} minutes" if deadline is not None else "No crossing predicted by countdown model")

plan = None
safety = None

if not emergency["emergency"]:
    print("STATUS: NORMAL")
else:
    plan = plan_recovery(position, velocity)
    print("GUIDANCE:", plan)

    safety = validate_independently(position, velocity, plan)
    print("SAFETY:", safety)
    print("RECOVERY FEASIBLE:", safety["authorized"])

    if safety["authorized"]:
        print("RECOVERY:", execute(position, velocity, plan))
    else:
        print("RECOVERY: ABORTED")

# AI mission assessment — advisory only. Server and model come from
# SINGULAROS_LLM_URL / SINGULAROS_LLM_MODEL (intelligence/llm.py).
import json

from intelligence.llm import LLMClient, LLMError

incident = {
    "communications": "LOST",
    "detected_hazards": emergency["hazards"],
    "initial_orbit": emergency["orbit"],
    "recovery_plan": plan,
    "safety_verification": safety,
    "time_to_120km_seconds": deadline,
    "recovery_feasible": safety["authorized"] if safety else None,
}

prompt = (
    "You are Singularity Return Home's emergency analysis AI. "
    "Summarize the emergency, recovery decision, and remaining risks "
    "in three concise sentences. Do not issue commands. "
    + json.dumps(incident)
)

try:
    summary = LLMClient().chat([{"role": "user", "content": prompt}])
    print("AI ASSESSMENT:", summary.strip())
except LLMError as error:
    print("AI UNAVAILABLE:", error)
    print("Deterministic mission control remains operational.")
