import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from math import sqrt, isfinite
from urllib.parse import urlsplit, parse_qs

from simulation.orbit import MU, EARTH_RADIUS, orbital_status
from safety.emergency import assess
from guidance.recovery import plan_recovery
from safety.validator import validate_independently
from navigation.deadline import time_to_altitude


def mission_snapshot(disturbance_m_s=150):
    radius = EARTH_RADIUS + 400
    position = (radius, 0, 0)
    velocity = (0, sqrt(MU / radius) - disturbance_m_s / 1000, 0)

    emergency = assess(position, velocity, communications=False)
    plan = plan_recovery(position, velocity)
    safety = validate_independently(position, velocity, plan)

    return {
        "mode": "SIMULATION",
        "disturbance_m_s": disturbance_m_s,
        "initial_orbit": orbital_status(position, velocity),
        "hazards": emergency["hazards"],
        "time_to_120km_seconds": time_to_altitude(position, velocity),
        "recovery_plan": plan,
        "safety_verification": safety,
        "recovery_feasible": safety["authorized"],
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != "/api/mission":
            self.send_error(404)
            return

        try:
            raw = parse_qs(url.query).get("disturbance", ["150"])[0]
            disturbance = float(raw)
            if not isfinite(disturbance) or not 0 <= disturbance <= 300:
                raise ValueError("Disturbance must be between 0 and 300 m/s")
        except ValueError as error:
            self.send_error(400, str(error))
            return

        payload = json.dumps(mission_snapshot(disturbance)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8000), Handler)
    print("Mission telemetry API: http://127.0.0.1:8000/api/mission", flush=True)
    server.serve_forever()
