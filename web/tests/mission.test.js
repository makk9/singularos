import test from 'node:test';
import assert from 'node:assert/strict';
import { createPlayback, missionState, parseFrozenTime } from '../src/mission.js';

test('frozen links accept finite seconds, clamp to the mission, and reject invalid values', () => {
  assert.equal(parseFrozenTime(null), null);
  assert.equal(parseFrozenTime(''), null);
  assert.equal(parseFrozenTime('Infinity'), null);
  assert.equal(parseFrozenTime('18junk'), null);
  assert.equal(parseFrozenTime('-9'), 0);
  assert.equal(parseFrozenTime('900'), 46);
  assert.equal(parseFrozenTime('18.5'), 18.5);
});

test('navigation fix and completion agree with the displayed mission', () => {
  assert.equal(missionState(0).phase, 0);
  assert.equal(missionState(18).phase, 2);
  assert.ok(missionState(10).errorKm > missionState(6).errorKm);
  assert.ok(missionState(20).errorKm < missionState(15).errorKm);
  assert.equal(missionState(22).errorKm, 1.2);
  assert.equal(missionState(27).burning, true);
  assert.equal(missionState(30).burning, false);
  assert.equal(missionState(41).complete, true);
  assert.equal(missionState(46).logs.at(-1).text, 'Splashdown. Mission complete.');
});

test('pause, seek, resume, and replay do not accumulate paused time', () => {
  const playback = createPlayback(0, true);
  playback.tick(1000);
  assert.equal(playback.tick(3000), 2);
  playback.setPlaying(false);
  assert.equal(playback.tick(9000), 2);
  playback.seek(26);
  assert.equal(playback.tick(10000), 26);
  playback.setPlaying(true);
  assert.equal(playback.tick(20000), 26);
  assert.equal(playback.tick(21000), 27);
  playback.seek(0);
  assert.equal(playback.tick(30000), 0);
});

test('loop wraps, and resetting the frame baseline prevents background-tab jumps', () => {
  const playback = createPlayback(45, true);
  playback.tick(0);
  assert.equal(playback.tick(2000), 1);
  playback.resetFrame();
  assert.equal(playback.tick(100000), 1);
  assert.equal(playback.tick(101000), 2);
});
