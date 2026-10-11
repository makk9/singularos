import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intelligence.llm import LLMClient, LLMError

incident = {
    "communications": "LOST",
    "altitude_km": 400,
    "original_perigee_km": -105.56,
    "proposed_delta_v_m_s": 92.37,
    "verified_recovery_perigee_km": 200.01,
    "maneuver_authorized": True,
}

prompt = (
    "You are Singularity Return Home's emergency assessment AI. "
    "Analyze this simulated spacecraft incident in three concise sentences. "
    "Explain the danger, recovery maneuver, and remaining limitations. "
    "Do not issue thruster commands. "
    + json.dumps(incident)
)

try:
    summary = LLMClient().chat([{"role": "user", "content": prompt}])
    print("AI ASSESSMENT:", summary.strip())
except LLMError as error:
    print("AI UNAVAILABLE:", error)
    print("Deterministic recovery remains independent.")
