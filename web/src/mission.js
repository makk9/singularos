export const TIMING = { coast: 5, fix: 14, plan: 22, burn: 26, reentry: 37, done: 41, loop: 46 };
export const PHASES = ['Boot', 'Coast', 'Fix position', 'Plan', 'Burn', 'Reentry'];
const LOG = [
  [0.3, 'Booted on unknown hardware. Probing devices.'],
  [1.6, 'Found camera, IMU, reaction wheels, and thruster.'],
  [3, 'No GPS lock. Ground link silent.'],
  [4.3, 'Switching to autonomous navigation.'],
  [6, 'Coasting. Tracking motion with the IMU.'],
  [10, 'Drift is growing. Position estimate degrading.'],
  [14.3, 'Matching star patterns to the onboard catalog.'],
  [16.5, 'Three stars matched. Attitude established.'],
  [18.5, 'Earth and Moon sighted. Resolving position.'],
  [21, 'Position fixed to within 1.2 km.'],
  [22.5, 'Computing a return trajectory.'],
  [25, 'Trajectory found. Preparing main engine.'],
  [26.2, 'Main burn started.'],
  [28.5, 'Burn complete. Coasting toward Earth.'],
  [37.2, 'Atmospheric entry. Heat shield holding.'],
  [40.5, 'Splashdown. Mission complete.'],
];
export const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
export const span = (time, start, end) => clamp((time - start) / (end - start));
export const ease = (value) => value * value * (3 - 2 * value);

export function parseFrozenTime(value) {
  if (value === null || value.trim() === '') return null;
  const time = Number(value);
  return Number.isFinite(time) ? clamp(time, 0, TIMING.loop) : null;
}

export function formatMET(time) {
  const minutes = Math.floor(Math.min(time, TIMING.done) * 20);
  return `T+${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}

export function missionState(time) {
  const boundaries = [0, 5, 14, 22, 26, 37];
  const phase = boundaries.findLastIndex((boundary) => time >= boundary);
  let errorKm = null;
  if (time >= TIMING.coast && time < TIMING.fix) {
    errorKm = 50 + 411950 * ease(span(time, TIMING.coast, TIMING.fix));
  } else if (time >= TIMING.fix && time < TIMING.plan) {
    errorKm = Math.max(1.2, 412000 * (1 - ease(span(time, 15, 21.2))) ** 3);
  } else if (time >= TIMING.plan) errorKm = 1.2;
  return {
    phase, errorKm,
    burning: time >= TIMING.burn && time < 28.5,
    complete: time >= TIMING.done,
    logs: LOG.filter(([at]) => at <= time).slice(-3).map(([at, text]) => ({ at, text })),
  };
}

export function createPlayback(initialTime, initiallyPlaying) {
  let time = clamp(initialTime, 0, TIMING.loop);
  let playing = initiallyPlaying;
  let previous = null;
  return {
    get time() { return time; },
    get playing() { return playing; },
    tick(now) {
      if (playing && previous !== null) time = (time + Math.max(0, now - previous) / 1000) % TIMING.loop;
      previous = now;
      return time;
    },
    seek(value) { time = clamp(value, 0, TIMING.loop); previous = null; },
    setPlaying(value) { playing = value; previous = null; },
    resetFrame() { previous = null; },
  };
}
