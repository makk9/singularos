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
| `mission.py`, `control/`, `intelligence/` | One-shot two-body recovery script and LLM assessment |
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
output directory.

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
