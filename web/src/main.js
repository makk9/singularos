import './style.css';
import { createScene } from './scene.js';
import { TIMING, PHASES, createPlayback, formatMET, missionState, parseFrozenTime } from './mission.js';

const $ = (id) => document.getElementById(id);
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const frozen = parseFrozenTime(new URLSearchParams(location.search).get('t'));
const playback = createPlayback(frozen ?? (reduceMotion.matches ? 25.5 : 0), frozen === null && !reduceMotion.matches);
const phaseButtons = [...document.querySelectorAll('#phases button')];
const captions = [
  'Discover the hardware. Establish control.',
  'No ground link. An expanding uncertainty.',
  'Read the stars. Find a position in the dark.',
  'A new trajectory. A way back to Earth.',
  'Commit to the burn. Trust the solution.',
  'Through the atmosphere. Back to where it began.',
];
let scene;
let available = false;
let contextLost = false;
let request = null;
let lastLog = '';

function updateUI(time) {
  const state = missionState(time);
  $('met').textContent = formatMET(time);
  $('err').textContent = state.errorKm === null ? 'NO FIX' : state.errorKm < 10 ? `${state.errorKm.toFixed(1)} km` : `${Math.round(state.errorKm).toLocaleString('en-US')} km`;
  $('err').classList.toggle('locked', time >= TIMING.plan);
  $('nav-status').textContent = state.complete ? 'MISSION COMPLETE' : time >= TIMING.plan ? 'POSITION LOCKED' : time >= TIMING.fix ? 'STAR MATCHING' : time >= TIMING.coast ? 'INERTIAL ONLY' : 'INITIALIZING';
  $('phase-code').textContent = `SEQ ${String(state.phase + 1).padStart(2, '0')} / 06`;
  $('scene-caption').textContent = state.complete ? 'Mission complete. Home, without a ground link.' : captions[state.phase];
  const logKey = state.logs.map(({ at }) => at).join(',');
  if (logKey !== lastLog) {
    lastLog = logKey;
    $('log').replaceChildren(...state.logs.map(({ at, text }) => {
      const li = document.createElement('li');
      const timestamp = document.createElement('time');
      timestamp.textContent = formatMET(at);
      li.append(timestamp, document.createTextNode(text));
      return li;
    }));
  }
  phaseButtons.forEach((button, index) => {
    const active = index === state.phase && !state.complete;
    button.classList.toggle('active', active);
    button.classList.toggle('done', index < state.phase || state.complete);
    if (active) button.setAttribute('aria-current', 'step');
    else button.removeAttribute('aria-current');
  });
  $('timeline').value = time;
  $('timeline').setAttribute('aria-valuetext', `${state.complete ? 'Mission complete' : PHASES[state.phase]}, ${time.toFixed(1)} seconds`);
  $('timeline').style.setProperty('--progress', `${time / TIMING.loop * 100}%`);
  $('elapsed').textContent = `${String(Math.floor(time)).padStart(2, '0')} / 46s`;
  $('play').setAttribute('aria-label', playback.playing ? 'Pause mission' : 'Play mission');
  $('play-text').textContent = playback.playing ? 'Pause' : 'Play';
  $('play-icon').textContent = playback.playing ? 'Ⅱ' : '▷';
  $('playback-status').textContent = contextLost ? '3D VIEW INTERRUPTED' : playback.playing ? 'AUTOPLAY / 46 SECOND LOOP' : 'PAUSED / EXPLORE THE MISSION';
  // Fade the scene at the loop seam; explicit stills remain fully visible.
  $('viewport').style.opacity = playback.playing ? Math.min(1, time / 0.8, (TIMING.loop - time) / 1.2) : 1;
}

function render() {
  if (available && !contextLost) scene.render(playback.time);
  updateUI(playback.time);
}

function schedule() {
  if (request === null && playback.playing && !document.hidden && !contextLost) request = requestAnimationFrame(frame);
}

function frame(now) {
  request = null;
  if (document.hidden || contextLost || !playback.playing) return;
  playback.tick(now);
  render();
  schedule();
}

function setPlaying(playing) {
  if (contextLost) return;
  playback.setPlaying(playing);
  if (request !== null) cancelAnimationFrame(request);
  request = null;
  render();
  schedule();
}

$('play').addEventListener('click', () => setPlaying(!playback.playing));
$('replay').addEventListener('click', () => {
  playback.seek(0);
  setPlaying(true);
});
$('timeline').addEventListener('input', (event) => {
  playback.seek(Number(event.target.value));
  setPlaying(false);
});
phaseButtons.forEach((button) => button.addEventListener('click', () => {
  playback.seek(Number(button.dataset.time));
  setPlaying(false);
}));

window.addEventListener('resize', () => {
  if (available && !contextLost) scene.resize();
  render();
});
document.addEventListener('visibilitychange', () => {
  playback.resetFrame();
  if (document.hidden && request !== null) {
    cancelAnimationFrame(request);
    request = null;
  } else schedule();
});
reduceMotion.addEventListener('change', () => {
  if (reduceMotion.matches) setPlaying(false);
});

function showFallback(message) {
  $('render-status').textContent = message;
  $('render-status').hidden = false;
  document.body.classList.add('render-fallback');
}

$('scene').addEventListener('webglcontextlost', (event) => {
  event.preventDefault();
  contextLost = true;
  playback.setPlaying(false);
  if (request !== null) cancelAnimationFrame(request);
  request = null;
  showFallback('The 3D view was interrupted. Your mission is paused while graphics recover.');
  $('play').disabled = $('replay').disabled = true;
  updateUI(playback.time);
});
$('scene').addEventListener('webglcontextrestored', () => {
  // Draw on the next frame, after Three.js has handled the restoration event
  // and rebuilt its GL state. Paused playback still needs this single redraw.
  requestAnimationFrame(() => {
    contextLost = false;
    $('render-status').hidden = true;
    document.body.classList.remove('render-fallback');
    $('play').disabled = $('replay').disabled = false;
    scene.restore();
    scene.resize();
    render();
  });
});

try {
  scene = createScene($('scene'), {
    invalidate: () => { if (available && !contextLost) render(); },
    onTextureError: () => {
      $('render-status').textContent = 'Some planet textures could not load. The mission remains available; reload to retry.';
      $('render-status').hidden = false;
    },
  });
  available = true;
} catch (error) {
  console.warn('3D scene unavailable:', error.message);
  showFallback('The 3D view is unavailable on this device. You can still play and explore the mission log below.');
}
render();
schedule();
