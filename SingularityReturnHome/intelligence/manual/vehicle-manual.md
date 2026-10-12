# Inspection craft: recovery manual (for the AI copilot)

## Vehicle and frame
- Small inspection craft near a space station in low Earth orbit.
- Station frame (metres): +x radial (away from Earth), +y along-track (direction of orbital motion). The dock port is at (0, 0). The craft docks nose-first with heading 180 degrees (nose pointing to -x), approaching from +x along the dock axis (y = 0).
- Staging point: (8, 0) on the dock axis. Pre-dock point: 0.8 m out on the dock axis.
- Four body thrusters: forward (pushes toward the nose), backward, left, right. An opposing pair is forward+backward or left+right. The craft can rotate freely; turning lets a working pair push in any direction.
- Orbital motion: an unpowered craft drifts and curves relative to the station. Holding position needs small burns.
- Station structure (keep clear by at least 2 m): core module x -13..-1, y -3..3; solar arrays x -12..-2 at y 5..13 (north) and y -13..-5 (south); radiator x -15..-13, y -6..6. The pre-planned inspection loop stays at least 5 m from the structure.

## Docking limits (all must hold, confirmed for 2 s)
- Distance to the dock at most 0.25 m, closing speed at most 0.05 m/s, heading within 0.05 rad of 180 degrees, fresh navigation.

## Procedure steps (the only actions available)
Parameters in brackets are the step's only fields; give each of them (speed_m_s is optional for GOTO). Each step starts where the previous one ended; the first step starts at the craft's current position.
- RETURN_TO_STAGING: fly back along the pre-planned loop to the staging point (8, 0). Safe path around the station. Use it as the first step whenever the report's ROUTE line says the straight line to staging is blocked.
- GOTO(x_m, y_m, speed_m_s): fly in a straight line from where the previous step ended to a point and stop. The straight line must stay at least 2 m clear of the station; the report's ROUTE line says whether the line to staging does.
- PREDOCK_STOP(speed_m_s): fly from the staging point to the pre-dock point on the dock axis and stop precisely there (0.8 m out; 1.5 m when followed by COAST_IN). Requires an intact opposing pair. Normal speed 0.1 m/s (at least 0.005). The pre-dock point is inside any near-dock speed-limit zone, so under an approach speed advisory set speed_m_s at or below the advisory limit.
- FINAL_APPROACH(speed_m_s): powered approach into the dock with the nose on the dock axis. Requires BOTH forward and backward thrusters (they control closing speed). With all four thrusters it may start from staging; with any thruster lost it must come directly after PREDOCK_STOP. Normal speed 0.1 m/s (at least 0.005).
- COAST_IN(speed_m_s): unpowered docking. From the pre-dock point, the craft uses its working pair to set a slow drift toward the dock (speed_m_s between 0.01 and 0.03 m/s: well below the 0.05 m/s docking limit, because the docking check needs 2 s of readings under the limit despite sensor noise), turns to the dock heading without thrusting, and coasts in. Must come directly after PREDOCK_STOP. Works when forward or backward (or both) are lost but an opposing pair remains. Use COAST_IN only when FINAL_APPROACH is unavailable: an unpowered coast cannot correct sideways orbital drift, and at slow speeds (for example under an approach speed cap) the drift often carries the craft off the dock axis and forces retries.
- HOLD_AT(x_m, y_m): fly in a straight line from where the previous step ended to a safe point, stop and keep station there indefinitely. Requires an intact opposing pair. Choose a point at least 5 m from the structure, e.g. the staging point (8, 0). If the straight line to it is blocked, put RETURN_TO_STAGING first: RETURN_TO_STAGING, HOLD_AT(8, 0).
- SAFE_STOP: brake with any working thruster, then shut down (abort). Use only when no opposing pair remains.

## Decisions
- DOCK: the last step must be FINAL_APPROACH or COAST_IN.
- HOLD: the last step must be HOLD_AT.
- ABORT: the plan must be SAFE_STOP.

## Station advisories
- Advisories from the station override normal procedure. Read every active advisory and cite the ones you followed in advisories_considered.
- If an advisory closes the dock, do not dock: HOLD at a safe point instead.
- If an advisory limits approach speed, the speed_m_s of every PREDOCK_STOP, COAST_IN and FINAL_APPROACH step must be at or below the limit.
- If an advisory defines a keep-out zone, no path segment may enter it.

## Rules
- You propose; a numerical validator checks every plan (capability, speeds, clearance, keep-out zones, fuel, advisories). If it rejects a plan, fix the problems it lists and propose again.
- Prefer docking when it is safe and allowed; otherwise HOLD; ABORT only when holding is impossible.
- Base your assessment on the evidence given (diagnosed thruster health, position, velocity, fuel), not on assumptions.
- The report's DOCKING, AVAILABLE STEPS, UNAVAILABLE STEPS, ROUTE and SPEED CAP lines are computed with the validator's own rules. Use only available steps, follow the ROUTE line, and respect the SPEED CAP.
- If the DOCKING line says docking is possible, propose DOCK with the step it names; a lost axial thruster alone is not a reason to HOLD, because COAST_IN docks without it. HOLD only when docking is not possible or not allowed.
