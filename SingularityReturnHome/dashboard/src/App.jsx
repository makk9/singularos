import { useState } from 'react'
import './App.css'

const mission = {
  altitude: 400,
  initialPerigee: -105.56,
  recoveredPerigee: 200.01,
  countdown: '23:53',
  deltaV: 92.37,
  fuelRemaining: 27.63,
}

function App() {
  const [disturbance, setDisturbance] = useState(150)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function runSimulation() {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`/api/mission?disturbance=${disturbance}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setResult(await response.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="dashboard">
      <header className="header">
        <div>
          <p className="eyebrow">SINGULARITY MACHINES / AUTONOMOUS SYSTEMS</p>
          <h1>SINGULARITY RETURN HOME</h1>
          <p className="subtitle">Autonomous Spacecraft Emergency Recovery</p>
        </div>
        <span className="status">● SIMULATION ACTIVE</span>
      </header>

      <section className="simulation-controls">
        <div style={{ marginBottom: '18px' }}>
          <label htmlFor="disturbance" style={{ display: 'block', marginBottom: '10px' }}>
            VELOCITY DISTURBANCE: <strong>{disturbance} m/s</strong>
          </label>
          <input
            id="disturbance"
            type="range"
            min="0"
            max="300"
            step="10"
            value={disturbance}
            onChange={(event) => {
              setDisturbance(Number(event.target.value))
              setResult(null)
            }}
            style={{ width: '100%', accentColor: '#00d4ff' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <small>0 m/s · NOMINAL</small>
            <small>300 m/s · SEVERE</small>
          </div>
        </div>
        <button onClick={runSimulation} disabled={loading}>
          {loading ? 'CALCULATING...' : '▶ RUN SIMULATION'}
        </button>
        {error && <p className="danger">API ERROR: {error}</p>}
        {result && (
          <p className="success">
            SIMULATION COMPLETE · Recovery {result.recovery_feasible ? 'AUTHORIZED' : 'REJECTED'}
          </p>
        )}
      </section>

      <section className="alert">
        <div>
          <p className="eyebrow">MISSION ALERT</p>
          <h2>COMMUNICATIONS LOST · UNSAFE TRAJECTORY</h2>
          <p>Autonomous recovery protocol initiated</p>
        </div>
        <div className="countdown">
          <span>TIME TO 120 KM</span>
          <strong>{result ? `${Math.floor(result.time_to_120km_seconds / 60)}:${String(Math.floor(result.time_to_120km_seconds % 60)).padStart(2, '0')}` : '--:--'}</strong>
        </div>
      </section>

      <section className="metrics">
        <article className="panel">
          <span>SPACECRAFT ALTITUDE</span>
          <strong>{result?.initial_orbit.altitude_km ?? '--'} <small>km</small></strong>
        </article>
        <article className="panel">
          <span>INITIAL PERIGEE</span>
          <strong className="danger">{result?.initial_orbit.perigee_km ?? '--'} <small>km</small></strong>
        </article>
        <article className="panel">
          <span>RECOVERED PERIGEE</span>
          <strong className={result?.recovery_feasible ? 'success' : 'danger'}>
            {result?.recovery_feasible
              ? (result.safety_verification.verified_orbit?.perigee_km
                ?? result.recovery_plan.predicted_orbit.perigee_km)
              : '--'} <small>km</small>
          </strong>
        </article>
        <article className="panel">
          <span>RECOVERY MANEUVER</span>
          <strong>{result?.recovery_plan.delta_v_m_s ?? '--'} <small>m/s</small></strong>
        </article>
      </section>

      <section className="details">
        <article className="panel trajectory">
          <h2>ORBITAL RECOVERY</h2>
          <div className="orbit-graphic">
            <div className="orbit orbit-safe"></div>
            <div className="orbit orbit-unsafe"></div>
            <div className="earth">EARTH</div>
            <div className="spacecraft">◆</div>
          </div>
          <div className="legend">
            <span><i className="line green"></i> Corrected trajectory</span>
            <span><i className="line red"></i> Initial trajectory</span>
          </div>
        </article>

        <article className="panel decisions">
          <h2>AUTONOMOUS DECISION LOG</h2>
          <div className="event"><span>01</span><p>Orbital anomaly detected</p><b>DETECTED</b></div>
          <div className="event"><span>02</span><p>Ground communications lost</p><b>CONFIRMED</b></div>
          <div className="event"><span>03</span><p>Recovery maneuver calculated</p><b>{result?.recovery_plan.delta_v_m_s ?? '--'} m/s</b></div>
          <div className="event"><span>04</span><p>Independent safety validation</p><b>{result ? (result.recovery_feasible ? 'AUTHORIZED' : 'REJECTED') : 'PENDING'}</b></div>
          <div className="event"><span>05</span><p>Simulated recovery burn</p><b>{result ? 'NOT EXECUTED' : 'PENDING'}</b></div>
          <div className="event"><span>06</span><p>Remaining fuel budget</p><b>{result?.recovery_feasible ? (120 - result.recovery_plan.delta_v_m_s).toFixed(2) : '--'} m/s</b></div>
          {result && !result.recovery_feasible && (
            <div className="notice">
              MANEUVER REJECTED
              <p>{result.safety_verification.reasons.join(' · ')}</p>
            </div>
          )}
          <div className="notice">
            LOCAL AI: ADVISORY ONLY
            <p>Deterministic safety controller retains maneuver authority.</p>
          </div>
        </article>
      </section>

      <footer>
        <span>MAXIMUM CONTROL, MINIMUM ABSTRACTION</span>
        <span>DEMONSTRATION DATA · TWO-BODY ORBIT MODEL · NOT FLIGHT SOFTWARE</span>
      </footer>
    </main>
  )
}

export default App
