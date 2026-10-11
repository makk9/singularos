import json
import urllib.request

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

payload = json.dumps({
    "model": "qwen3.8:27b",
    "prompt": prompt,
    "think": False,
    "stream": False
}).encode()

try:
    request = urllib.request.Request(
        "http://10.0.2.2:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    print("AI ASSESSMENT:", result["response"].strip())
except Exception as error:
    print("AI UNAVAILABLE:", error)
    print("Deterministic recovery remains independent.")
