# SingularOS — Mission & Problem Specification

This document is the shared, binding definition of the problem SingularOS solves. Every implementation, PR, and design decision must be consistent with it. If your branch needs to deviate from something here, raise it with the team and update this doc in the same PR — don't silently diverge.

Where this doc says "fixed," treat it as a hard constraint. Where it says "open," teams/individuals may choose freely as long as the interface contract is respected.

---

## 1. Mission statement

SingularOS is a standalone autonomous emergency recovery application for a small autonomous inspection spacecraft. It detects abnormal vehicle behavior after unexpected damage, figures out which sensors and actuators can still be trusted, and assembles and executes a return-to-dock procedure — revising that plan as new evidence, new faults, or moving obstacles appear. It docks when feasible, or selects a defined safe fallback when it isn't.

**Central challenge:** recover without knowing in advance exactly what broke, which measurements to trust, or which procedure will work.

## 2. Explicit non-goals (fixed)

- **Not flight-qualified software.** This is a simulation prototype for a hackathon.
- **Not full orbital mechanics.** 2D in-plane relative motion near the station only: linearised Clohessy–Wiltshire (Hill) dynamics about the station's circular orbit. No orbit propagation, out-of-plane motion, eccentricity, drag or other perturbations. These omissions must be documented wherever physics is described — don't let them get silently assumed away.
- **Not Omarchy-dependent.** Omarchy is a *future* operator environment. Do not require installing it, and do not spend hackathon time on desktop/OS integration.
- **Not an unrestricted random-failure generator.** Faults are configured and reproducible (seeded), not arbitrary chaos, and the full recovery loop must work before fault variety is expanded.
- **The LLM is not the flight controller.** It never executes per-timestep control and never invents numerical feasibility results. Those come only from the numerical planner/validator.

## 3. Mission scenario (fixed narrative)

A small autonomous inspection spacecraft departs its home docking station on a routine inspection pass. Partway through, an undetected particle impact damages an unknown combination of sensors and actuators — some systems fail completely, others become intermittent, stale, biased, or otherwise unreliable, in ways not revealed to the agent.

SingularOS detects the abnormal behavior and activates emergency recovery. Its LLM agent interprets diagnostic evidence, consults vehicle procedures/documentation, and coordinates tools to determine which capabilities remain trustworthy. It constructs a return procedure using surviving systems; numerical tools estimate state, validate trajectories, and execute maneuvers. As observations change, additional malfunctions occur, or a tracked obstacle threatens the path, SingularOS revises its strategy. It returns and docks when feasible, or selects a defined fallback when docking cannot be done safely.

## 4. World model conventions (fixed)

- **Environment:** 2D local proximity space around a dock on a station in circular orbit. Relative motion follows the Clohessy–Wiltshire equations, so an unpowered vehicle drifts relative to the station.
- **Reference frame:** station-centered and moving with the station; dock at the origin. Axis convention: +x radial (away from Earth), +y along-track (direction of orbital motion).
- **Units:** SI only — meters, seconds, kilograms, newtons, radians (and rad/s for angular rate).
- **Thruster directions:** body-frame, forward/backward/left/right; rotate with vehicle orientation (not world-frame fixed).
- **Timestep:** fixed simulation timestep, decoupled from the (slower) agent decision cadence. Exact values are config (see §9), but the separation itself is fixed.
- **Reproducibility:** every scenario run is defined by a saved random seed + scenario config file. No implementation may rely on unseeded randomness for anything that affects grading/comparison.
- **Hidden truth vs. observation (hard boundary):** the simulator maintains physically consistent ground truth — position, velocity, orientation, angular velocity, fuel, battery (when present), *actual* hardware health, obstacle state. Nothing in this list is ever exposed to the agent or the dashboard's "what the agent sees" view. Agents and controllers act only on observations (§6).
- **No teleportation / no truth-overwriting:** sensor faults may only alter what is *reported*. Actuator faults may only alter the vehicle's *physical response*. Neither may discontinuously alter the true kinematic state.

## 5. Spacecraft specification (fixed inventory, open internal parameters)

| Component | Purpose | Initial failure scope |
|---|---|---|
| 4× directional thrusters | Body-relative forward/backward/left/right acceleration | Exactly one unavailable or degraded in the baseline scenario |
| Attitude control | Rotates vehicle to redirect surviving thrust | Healthy initially; bounded rotation rate |
| Attitude sensor | Observes orientation + angular velocity | Healthy initially |
| Station-relative navigation | Position/velocity estimate | Healthy initially; later scenarios add dropouts, freezes, or bias |
| Docking camera | Dock-relative observation, limited visibility range | Intermittent availability |
| Station beacon | Independent modeled bearing-or-range observation (pick one and document it — see §6) | Healthy initially |
| Fuel monitor | Remaining maneuvering fuel | Healthy initially |
| Battery monitor | Remaining electrical energy | Added in later milestone |
| Actuator feedback | Ack / limited actuator status only | Must never reveal perfect hidden actuator health |

Fixed requirements regardless of exact numbers chosen:
- Rotation takes nonzero time and consumes a documented resource (fuel and/or battery — pick one and document it).
- Each thruster has: max output, fuel consumption rate, response delay, and actual effectiveness (which may be degraded by a fault).
- The beacon's measurement type must be specified precisely (e.g. "bearing-only, ±X° uncertainty" vs. "range+bearing"). A bearing-only reading must never be silently treated as a full position fix anywhere in the code.
- Sensors that share an underlying hardware/navigation source must share correlated failures — don't fault two co-dependent readings independently as if they were unrelated.

Exact numeric values (max thrust, fuel capacity, rotation rate limit, camera FOV/range, timestep length, etc.) are **open** — define them in scenario config, not hardcoded, and document defaults in `PROGRESS.internal.md` or module READMEs.

## 6. Observation & fault model contract (fixed)

Every observation, from every source, carries exactly these fields:

- `source` — identifier of the sensor/system
- `timestamp` — measurement time
- `available` — boolean
- `value` — measurement value(s), or absent/null when unavailable
- `uncertainty` — estimated uncertainty on the value

Fault types the simulator must be able to express (all configurable + seeded, all independent of this list for *which* component they hit):

- **Complete loss** — sensor/actuator stops working entirely.
- **Intermittent dropout** — unavailable for meaningful stretches of time, not single-tick blips.
- **Frozen/stale** — repeatedly emits an old value, potentially with a *fresh* timestamp. (This is intentional: detecting staleness must require cross-checking against other evidence, not just reading the timestamp.)
- **Persistent or drifting bias.**
- **Reduced or intermittent actuator effectiveness.**

Scenarios must include both recoverable cases and intentionally infeasible ones (where the correct agent behavior is to fall back, not to "succeed" anyway).

## 7. Architecture contract (fixed responsibilities, open implementation)

| Module | Responsibility |
|---|---|
| Simulator | Dynamics, hidden truth, observations, faults, obstacles |
| State estimator | Estimated vehicle state + uncertainty |
| Fault monitor | Anomaly detection from available evidence only |
| Emergency supervisor | Recovery activation + mode transitions |
| LLM recovery agent | Hypotheses, diagnostic selection, procedure interpretation, plan revision |
| Numerical planner & validator | Capability, fuel, trajectory, and collision checks |
| Controller | Continuous bounded maneuver execution |
| Command arbiter | Guarantees exactly one controller owns actuator authority at a time |
| Dashboard & event log | Shows observations, estimates, decisions, maneuvers, outcomes |

**Hard rule:** the LLM proposes and interprets; it never directly drives actuators and never asserts a numeric feasibility/trajectory result on its own authority — those always come from the numerical planner/validator module.

**Hard rule:** after an emergency takeover, a restarted/reconnected mission controller must not be able to silently reclaim actuator authority. The command arbiter is the single source of truth for who's in control.

## 8. Recovery mode state machine (fixed)

```
NORMAL → INVESTIGATE → RETURN → APPROACH → DOCKED
```

- Transitions back to `INVESTIGATE`/replanning are allowed from any later state when evidence changes.
- `HOLD` and `ABORT` are explicit defined outcomes, not implicit defaults.
- `HOLD` is **not** automatically safe — its controller behavior must be specified, and its feasibility under current sensing/actuation must be checked, not assumed.
- Docking success requires configurable thresholds for: distance, relative speed, alignment, and estimation confidence — plus sufficiently fresh supporting observations. (Exact threshold values are config/open; the requirement that all four dimensions are checked is fixed.)
- Expired or infeasible plans must be rejected by the arbiter/validator, not executed anyway.

## 9. What's intentionally open (your implementation's own choices)

- Programming language, UI stack, simulator framework.
- Exact vehicle/scenario parameter values and timestep length.
- Exact sensor visibility/measurement models (within the contract in §6).
- Exact docking thresholds and fallback behavior (within the requirement in §8).
- LLM provider, tool schemas, timeouts, and fallback behavior when the model is unavailable.
- Internal algorithms for estimation, planning, and control.

Document your own choices as you go (module README or `PROGRESS.internal.md`), since four people are building independent versions in parallel.

## 10. Build order (fixed sequence — don't skip ahead)

1. Normal departure and return, no faults.
2. One failed/degraded directional thruster; return using surviving actuators.
3. LLM investigation + recovery planning wired in.
4. Intermittent docking-camera observations.
5. One tracked moving obstacle requiring replanning.
6. (Stretch) Battery constraints + additional fault combinations.

Target first full demo = thruster fault + intermittent camera + moving obstacle, combined.

## 11. Evaluation contract (fixed)

The hypothesis under test: an LLM can interpret evidence/documentation and assemble recovery procedures for unfamiliar fault combinations with less scenario-specific hand coding than a conventional approach.

This is **not** proven by "it survived some random failures." Every comparison must run the LLM-based agent and a clearly documented deterministic baseline on identical seeds/scenarios, and record:

- Recovery/docking success
- Collisions and limit violations
- Appropriate fallback decisions
- Fuel consumption
- Recovery time and agent decision latency
- Diagnostic actions taken and plans rejected

The baseline's own capabilities must be documented explicitly so conclusions are comparing like-for-like.

## 12. Glossary (keep names consistent across implementations)

- **Truth** — the simulator's hidden, exact state. Never exposed to agent/dashboard-as-seen-by-agent.
- **Observation** — a timestamped, possibly-unavailable, possibly-wrong reading conforming to §6.
- **Estimate** — the state estimator's output derived from observations; carries its own uncertainty, is itself not truth.
- **Plan** — a candidate recovery procedure submitted to the numerical validator before execution.
- **Fallback** — a defined safe non-docking outcome, chosen when docking is infeasible.
- **Arbiter** — the single owner of actuator command authority.

---

*Changes to this document should go through a PR like any other change, since it's the contract the other three implementations depend on.*
