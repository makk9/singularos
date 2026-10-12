# Singularity Return Home

Autonomous recovery simulator for a small inspection spacecraft working
around a station in low Earth orbit. The craft flies an inspection loop,
detects faults from its own observations, diagnoses what still works, and
returns to dock, holds in a safe state, or aborts. Faults range from a dead
thruster near the station to a debris strike that puts the craft on a
reentry path.

The simulator (`singularos_sim/`) is the 2D simulator from `sim_1/`
(see [MISSION.md](../MISSION.md)), extended to orbit scale. The orbit-scale
recovery uses the two-body modules in this directory: `simulation/orbit.py`,
`guidance/recovery.py`, `safety/validator.py` and `navigation/deadline.py`.

## Layout

| Path | Contents |
|---|---|
| `singularos_sim/` | Simulator: dynamics, sensors, controller, planner, runner, replay |
| `scenarios/` | Scenario files (TOML); each run is defined by a scenario and a seed |
| `simulation/orbit.py` | Two-body orbit status (altitude, eccentricity, perigee) |
| `guidance/recovery.py` | Prograde burn that raises perigee to 200 km |
| `safety/validator.py` | Independent re-verification of a proposed burn |
| `navigation/deadline.py` | Time until the orbit descends through a given altitude |
| `telemetry/api.py` | HTTP API for the dashboard |
| `dashboard/` | React dashboard |
| `intelligence/` | LLM client (Ollama or OpenAI-compatible), recovery-proposal harness, check review, advisor |
| `mission.py`, `control/` | One-shot two-body recovery script |
| `tests/` | pytest suite |

## Running

Python 3.11 or newer. From this directory:

```sh
uv venv .venv && uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/python -m pytest
.venv/bin/python -m singularos_sim scenarios/orbital_strike_safe_orbit.toml
```

The CLI prints the outcome and writes `runs/<scenario>-seed<seed>/` with
`config.json`, `log.jsonl` (one line per step, truth and observations
separate), `summary.json` and `replay.html` (self-contained, opens in a
browser). `--seed N` overrides the scenario seed; `--out DIR` sets the
output directory; `--all` runs every scenario, prints a result table and
links the replays through a scenario picker. The replay shows truth and the
controller's belief side by side: system health, thruster output vs.
command, and station-frame (LVLH) navigation.

Dashboard:

```sh
.venv/bin/python -m telemetry.api          # http://127.0.0.1:8000
cd dashboard && npm ci && npm run dev      # http://127.0.0.1:5173, proxies /api
```

API endpoints:

| Endpoint | Returns |
|---|---|
| `GET /api/mission?disturbance=150` | One-shot two-body recovery analysis |
| `GET /api/scenarios` | Scenario names, expected outcomes, faults |
| `GET /api/run?scenario=NAME[&seed=N]` | Runs the scenario (or reuses a finished run): summary, track sampled every 1 s, controller events |
| `GET /api/replay?scenario=NAME[&seed=N]` | The run's `replay.html` |

## LLM advisor

The LLM proposes and interprets; it never drives actuators and never
asserts feasibility (MISSION.md section 7). With `--llm`, the controller asks
it for a proposal at each decision point (orbit triage, recovery plan) and
logs the reply as an `llm_advice` event next to the deterministic decision,
which keeps actuator authority. Without a reachable server and model, the
run continues deterministic-only.

```sh
ollama pull hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M    # once, 5.7 GB
ollama serve                                        # if not already running
.venv/bin/python -m singularos_sim scenarios/orbital_strike_safe_orbit.toml --llm
```

Settings (environment):

| Variable | Default | |
|---|---|---|
| `SINGULAROS_LLM_URL` | `http://127.0.0.1:11434` (`openai`: `http://127.0.0.1:8080`) | From inside a QEMU guest (user-mode networking): `http://10.0.2.2:11434` |
| `SINGULAROS_LLM_MODEL` | `hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M` | Any name from `ollama list` |
| `SINGULAROS_LLM_BACKEND` | `ollama` | `openai` for an OpenAI-compatible server, e.g. llama.cpp in `docker/` |
| `SINGULAROS_LLM_THINK` | `false` | Ollama `think` option; `default` to not send it. With thinking on, Qwen3.5 9B did not return a schema-constrained reply within 300 s |
| `SINGULAROS_LLM_TIMEOUT` | `180` | Seconds per request |

Pipeline (`intelligence/`, harness from PR #3):

1. `llm.py` sends the chat with the proposal schema as structured output
   (Ollama: `POST /api/chat` with `format`; OpenAI-compatible:
   `response_format` `json_schema`).
2. `harness.py` re-checks the reply against the schema in Python, then
   semantic rules (e.g. `DOCKED` must request `DOCK_ALIGNMENT` and
   `OBSERVATION_FRESHNESS`; `RAISE_PERIGEE` must request `FUEL_BUDGET` and
   `ORBIT_SAFETY` and mode `HOLD`), retrying with feedback up to twice.
3. `review.py` runs the requested checks against the planner's numbers
   (delta-v budget, orbit safety, independent perigee-raise validation,
   thruster health, docking criteria) and records whether the proposal
   agrees with the deterministic decision. `COLLISION_CHECK` reports not
   evaluated: routes are pre-planned.

`schemas/recovery-proposal.json` (version 2): mode from the MISSION.md
section 8 vocabulary; plan actions include `BRAKE` and `RAISE_PERIGEE`;
`max_delta_v_mps` up to 1000 and `max_relative_speed_mps` up to 20 for
orbit-scale recovery.

`mission.py` and `intelligence/assess.py` use the same client for their
incident summaries. Tests run against an in-process fake Ollama server; set
`SINGULAROS_LLM_INTEGRATION=1` to also test the configured live server.

## Scenario launcher

```sh
ollama serve                              # for AI copilot runs
.venv/bin/python -m telemetry.api         # then open http://127.0.0.1:8000
```

Pick a scenario, tick **AI copilot (LLM)** or leave it off for the baseline,
choose a seed and a live speed, and press **Run & play**. The run is **live**:
the server simulates it in the background, paced to the chosen speed, and
streams it to the replay as it happens (a red LIVE badge shows while it runs).
When the AI copilot is asked for a plan, the craft holds position and
simulated time runs at real speed, so the wait you see is the model's real
thinking time; proposals and the validator's verdicts appear as they happen.
Every live run is saved (`runs/<scenario>[-copilot]-seed<N>-r<k>`) and replays
like any other run afterwards. **Runs: N** plays N live runs one after another.
**Cancel** stops the live run at once, even while the AI copilot is thinking,
and skips any remaining runs; the unfinished run is discarded
(`/api/live/cancel?id=<session>`).

**Track overlay** (replay footer, in replays opened through the launcher):
a dropdown listing the other runs of the same scenario, filtered by scope
(this seed or all seeds) and mode (baseline or AI copilot), with Select all
and Clear. Each selected run is drawn as a coloured track with a "ghost"
marker showing where that run was at the current time; a legend on the map
gives each run's outcome and the time it first diverged from this run by more
than 1 m (click to jump there). `?overlay=all` pre-selects every other run.

**History** slides over the replay and shows every run of the selected
scenario, seed and mode (or all seeds): pass rate, number of distinct
trajectories (repeated baseline runs are identical), outcome spread, the
copilot's first proposals, accepted plans and rejection reasons, LLM time,
all paths overlaid, and a list to replay any run. The URL can pre-fill the
form: `?scenario=NAME&copilot=1&seed=N&history=1`. `python -m telemetry.api
PORT` serves on another port.

## AI copilot

With `--copilot`, the LLM does more than advise: at the recovery decision it
proposes a multi-step plan, and if a deterministic validator accepts it, the
controller flies it. The copilot proposes; it never drives actuators and never
asserts feasibility (MISSION.md section 7).

1. After the fault is detected and diagnosed, the controller sends the copilot
   its evidence: diagnosed thruster health, observed position, velocity and
   fuel, and the text of any station advisories, together with the vehicle
   manual (`intelligence/manual/vehicle-manual.md`). The report also carries
   planning facts computed with the validator's own rules
   (`plan_validator.planning_facts`): the steps the diagnosed thrusters and
   advisories allow, whether the straight line to staging clears the station,
   and any approach speed cap with the steps it applies to. It does not send
   the baseline's own decision, and never truth.
2. The copilot replies with a plan matching
   `intelligence/schemas/copilot-plan.json`: an assessment, a decision (DOCK,
   HOLD, ABORT), steps from a fixed library (RETURN_TO_STAGING, GOTO,
   PREDOCK_STOP, COAST_IN, FINAL_APPROACH, HOLD_AT, SAFE_STOP), the advisories
   it followed, and a rationale.
3. `singularos_sim/plan_validator.py` checks structure, prerequisites,
   thruster capability, speed limits, advisories, station clearance and fuel.
   A rejected plan's problems go back to the copilot, up to
   `recovery.copilot_max_attempts`. When the problems concern only the steps,
   the feedback tells it to keep its decision.
4. An accepted plan is flown and the copilot holds actuator authority. With no
   accepted plan, an error, or no reachable model, the baseline plan is used.
   If the copilot's plan exhausts its docking retries, authority returns to
   the baseline (HOLD).

Station advisories (`[[advisories]]` in a scenario) carry text for the
copilot and structured constraints for the validator (`max_approach_speed`,
`dock_closed`, `keep_out`). The baseline does not act on them. Advisory
compliance is scored on truth and fails a run.

```sh
ollama serve                                             # model as in "LLM advisor"
.venv/bin/python -m singularos_sim scenarios/copilot_coast_in.toml --copilot
.venv/bin/python -m singularos_sim scenarios/copilot_coast_in.toml --copilot \
    --copilot-plan intelligence/examples/coast_in.json   # scripted plan, no model
```

| Scenario | Fault and advisory | Baseline | Copilot (correct plan) |
|---|---|---|---|
| `copilot_coast_in` | backward thruster lost | HOLD (cannot dock without both axial thrusters) | DOCKED by coast-in |
| `copilot_advisory_speed` | left thruster lost; approach at most 2 cm/s within 3 m | DOCKED but breaks the speed limit | DOCKED within the limit |
| `copilot_trap_dock_closed` | left thruster lost; dock closed | DOCKED although the dock is closed | HOLD at a safe point |

The replay's AI copilot panel shows actuator authority, station messages, each
proposal with its steps and reasoning, and the validator's verdict with the
reasons for any rejection; the accepted plan is drawn on the map.

Limits: sim time pauses while the model answers (latency is logged, not
simulated); the step library is fixed; with scripted plans the copilot shows
the mechanism, not the model's reasoning.

## Physics

2D, in-plane, in a frame centred on the station's dock: +x radial (away from
Earth), +y along-track. The station is on a circular orbit of period
`[orbit] period_s` (default 5554 s, about 400 km altitude).

The vehicle follows the exact nonlinear equations of relative motion for
two-body gravity (`singularos_sim/orbit.py`):

```
x'' =  2n y' + n²(R + x) − μ(R + x)/r³ + aₓ
y'' = −2n x' + n² y      − μ y/r³       + a_y
```

with `n` the station's mean motion, `R` its orbit radius and `r` the
vehicle's distance from Earth's centre. Within tens of metres of the station
this agrees with the Clohessy-Wiltshire equations to well under a millimetre.
At orbit scale it does not: for a 150 m/s retrograde strike, the linear model
is about 2.5 km off by the time the craft reaches 120 km altitude.

Also modelled: four body-frame thrusters with thrust, fuel rate, response
delay and true health; rate-limited attitude; mass from remaining fuel;
seeded Gaussian sensor noise; station geometry for truth-side collision
checks. Integrator: semi-implicit Euler at `sim_dt_s`.

Not modelled: out-of-plane motion, J2, drag, third bodies, imaging. Reentry
is the vehicle descending through 120 km; the run ends there.

## Controller

The controller sees only sensor observations and the nominal vehicle spec,
never truth, fault configuration or true thruster health.

- **Inspection loop:** depart to staging, fly the route in
  `[[mission.route]]` (inspect stops and via corners), return and dock.
- **Fault monitor:** observed velocity change over a sliding window vs. the
  change predicted from its own commands, its thruster health estimates and
  orbital motion.
- **Orbit triage** (`planner.assess_orbital`): if the vehicle's own orbit has
  a perigee below `[orbital] safe_perigee_km` (default 200 km), the first
  response is chosen from the delta-v budget (rocket equation on observed
  fuel above the reserve):
  - `BRAKE`: null the velocity relative to the station, which restores the
    station's orbit, then investigate as below. Chosen if braking x margin
    fits the budget and finishes before reentry.
  - `SAFE_ORBIT`: prograde burn planned by `guidance/recovery.py` and
    authorised by `safety/validator.py` against the budget; the craft holds
    in that orbit with thrusters off.
  - `ABORT`: neither fits; the time to reentry from
    `navigation/deadline.py` is logged.
- **Investigation:** brake, then fire each thruster alone and compare
  measured with expected velocity change (orbital acceleration removed) to
  estimate its health.
- **Plan** (`planner.assess_recovery`): RETURN and dock if both axial
  thrusters work and the return fuel x margin fits; else HOLD (station-keep
  at a loop point) if an opposing thruster pair and fuel remain; else ABORT.
  From beyond `far_range_m` (200 m), the return first flies straight in to
  `far_approach_radius_m` (100 m) at `far_transit_speed_m_s` (10 m/s), then
  follows the loop; its fuel estimate includes about 2n per metre for
  orbital motion.

## Scenarios

| Scenario | Fault | Expected |
|---|---|---|
| `nominal` | none | DOCKED |
| `thruster_fault` | small impact, left thruster dead | DOCKED |
| `thruster_degraded` | small impact, forward thruster at 40% | DOCKED |
| `thruster_fault_two_lateral` | small impact, both lateral thrusters dead | DOCKED |
| `thruster_fault_infeasible` | small impact, backward thruster dead | HOLD |
| `thruster_fault_two_axial` | small impact, both axial thrusters dead | HOLD |
| `thruster_fault_abort` | small impact, forward, backward and left dead | ABORT |
| `orbital_base` | none, orbit-scale thrusters (40 N) and 20 kg fuel | DOCKED |
| `orbital_strike_return` | 150 m/s retrograde strike | DOCKED via BRAKE |
| `orbital_strike_safe_orbit` | 150 m/s strike, 3.2 kg fuel | HOLD in safe orbit |
| `orbital_strike_abort` | 300 m/s strike, 3.2 kg fuel | ABORT, reentry |

`orbital_base` raises `[recovery] monitor_threshold_m_s` to 0.3 m/s: the
40 N thrusters' 0.1 s response delay alone produces up to ~0.1 m/s of
monitor residual. Scenario files may start with `extends = "base.toml"`;
tables merge key by key.
