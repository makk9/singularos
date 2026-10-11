import { useEffect, useState } from 'react'

const EVENT_TEXT = {
  anomaly_detected: (e) => `Anomaly: motion differs from commands by ${e.residual_m_s.toFixed(2)} m/s`,
  orbital_triage: (e) => `Orbit triage: ${e.decision}. ${e.reasons.join('; ')}`,
  llm_advice: (e) => (e.error
    ? `LLM advice (${e.point}): unavailable, ${e.error}`
    : `LLM advice (${e.point}, advisory only): ${e.proposal.mode} / ${e.proposal.plan.action}, `
      + (e.review.agrees_with_deterministic ? 'agrees' : `differs from ${e.review.deterministic_mode}`)
      + (e.review.failed.length ? `; failed checks: ${e.review.failed.join(', ')}` : '')),
  investigate_start: () => 'Investigating: braking, then testing thrusters',
  diagnostic: (e) => `${e.thruster} thruster: ${e.estimate === 0 ? 'FAILED' : `${Math.round(e.estimate * 100)}%`} (${e.method})`,
  plan: (e) => `Plan: ${e.decision}. ${e.reasons.join('; ')}`,
  hold_established: (e) => (e.kind === 'safe_orbit'
    ? `Holding in safe orbit, perigee ${e.orbit.perigee_km.toFixed(1)} km`
    : 'Holding at safe point'),
  abort: (e) => `ABORT: ${e.reason}`,
  abort_safe: () => 'Abort: braked, thrusters off',
  dock_retry: (e) => `Docking retry ${e.retry}`,
  dock_retry_limit: () => 'Docking retries exhausted: HOLD',
}

function formatTime(seconds) {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
}

function Track({ track }) {
  const W = 520
  const H = 300
  const pad = 16
  // Along-track (y) runs left to right, radial (x, away from Earth) runs up.
  const ys = track.map((p) => p.y_m).concat(0)
  const xs = track.map((p) => p.x_m).concat(0)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const span = Math.max(maxY - minY, maxX - minX, 1)
  const scale = Math.min((W - 2 * pad) / Math.max(maxY - minY, span * 0.2), (H - 2 * pad) / Math.max(maxX - minX, span * 0.2))
  const px = (p) => pad + (p.y_m - minY) * scale
  const py = (p) => H - pad - (p.x_m - minX) * scale
  const points = track.map((p) => `${px(p).toFixed(1)},${py(p).toFixed(1)}`).join(' ')
  const end = track[track.length - 1]
  const dock = { x_m: 0, y_m: 0 }
  const extent = span >= 1000 ? `${(span / 1000).toFixed(1)} km` : `${span.toFixed(0)} m`
  return (
    <svg className="track" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Vehicle track relative to the station, spanning ${extent}`}>
      <polyline points={points} fill="none" stroke="#63d9ff" strokeWidth="1.5" />
      <circle cx={px(dock)} cy={py(dock)} r="5" fill="none" stroke="#49e6a1" strokeWidth="2" />
      <text x={px(dock) + 8} y={py(dock) - 8} className="track-label">Station</text>
      {end && <circle cx={px(end)} cy={py(end)} r="4" fill="#ffffff" />}
      <text x={W - pad} y={H - 4} textAnchor="end" className="track-label">span {extent}</text>
    </svg>
  )
}

export default function ScenarioRuns() {
  const [scenarios, setScenarios] = useState([])
  const [selected, setSelected] = useState('orbital_strike_safe_orbit')
  const [run, setRun] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/scenarios')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then(setScenarios)
      .catch((err) => setError(err.message))
  }, [])

  async function runScenario() {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`/api/run?scenario=${encodeURIComponent(selected)}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setRun(await response.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const s = run?.summary
  const passed = s && s.outcome === s.expected_outcome && !s.collision
  return (
    <section className="scenario-runs">
      <div className="panel">
        <h2>SIMULATOR SCENARIOS</h2>
        <div className="scenario-controls">
          <label htmlFor="scenario">Scenario</label>
          <select
            id="scenario"
            value={selected}
            onChange={(event) => {
              setSelected(event.target.value)
              setRun(null)
            }}
          >
            {scenarios.map((sc) => (
              <option key={sc.name} value={sc.name}>{sc.name} (expected {sc.expected_outcome})</option>
            ))}
          </select>
          <button onClick={runScenario} disabled={loading || !scenarios.length}>
            {loading ? 'RUNNING...' : '▶ RUN SCENARIO'}
          </button>
          {s && (
            <a className="replay-link" href={`/api/replay?scenario=${encodeURIComponent(selected)}`} target="_blank" rel="noreferrer">
              Open replay
            </a>
          )}
        </div>
        {error && <p className="danger">API ERROR: {error}</p>}
      </div>

      {s && (
        <>
          <div className="metrics">
            <article className="panel">
              <span>OUTCOME</span>
              <strong className={passed ? 'success' : 'danger'}>{s.outcome}</strong>
              <small>expected {s.expected_outcome}</small>
            </article>
            <article className="panel">
              <span>SIM TIME</span>
              <strong>{formatTime(s.sim_time_s)}</strong>
              <small>{s.reentry ? `reentry at ${formatTime(s.reentry.t)}` : 'no reentry'}</small>
            </article>
            <article className="panel">
              <span>PERIGEE AT END</span>
              <strong className={s.orbit_at_end.perigee_km >= 200 ? 'success' : 'danger'}>
                {s.orbit_at_end.perigee_km.toFixed(1)} <small>km</small>
              </strong>
            </article>
            <article className="panel">
              <span>FUEL USED</span>
              <strong>{s.fuel_used_kg.toFixed(2)} <small>kg</small></strong>
              <small>{s.fuel_remaining_kg.toFixed(2)} kg left</small>
            </article>
          </div>
          <div className="details">
            <article className="panel trajectory">
              <h2>TRACK RELATIVE TO STATION</h2>
              <Track track={run.track} />
            </article>
            <article className="panel decisions">
              <h2>CONTROLLER DECISIONS</h2>
              {run.events.filter((e) => EVENT_TEXT[e.type]).map((e, i) => (
                <div className="event" key={i}>
                  <span>{formatTime(e.t)}</span>
                  <p>{EVENT_TEXT[e.type](e)}</p>
                </div>
              ))}
              {!run.events.length && <p className="subtitle">No faults detected.</p>}
            </article>
          </div>
        </>
      )}
    </section>
  )
}
