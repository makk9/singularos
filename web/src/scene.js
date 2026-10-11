import * as THREE from 'three';
import { TIMING, span, ease, missionState } from './mission.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { canvasTexture, randomGenerator, surfaceTextures } from './visuals/textures.js';
import { createEarth } from './visuals/earth.js';
import { createSpacecraft } from './visuals/spacecraft.js';

const CYAN = 0x79f4ef;
const v = (x, y, z) => new THREE.Vector3(x, y, z);
const RADIUS = 2.45;

export function createScene(canvas, { invalidate = () => {}, onTextureError = () => {} } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x020409);
  const camera = new THREE.PerspectiveCamera(37, 1, 0.1, 300);
  const textures = surfaceTextures();
  for (const texture of [textures.solar, textures.hull, textures.foil]) {
    texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);
  }
  const sunDirection = v(-3.8, 3.2, 1.6).normalize();
  const planet = createEarth(RADIUS, sunDirection, renderer, invalidate, onTextureError);
  scene.add(planet.earth);
  const moon = new THREE.Mesh(new THREE.SphereGeometry(0.62, 64, 32), new THREE.MeshStandardMaterial({
    color: 0xb5b4b2, map: textures.moon, bumpMap: textures.moon, bumpScale: 0.025, roughness: 1,
  }));
  moon.position.set(3.8, 2, -8);
  scene.add(moon);

  scene.add(new THREE.AmbientLight(0x6a8bb5, 0.12));
  const sun = new THREE.DirectionalLight(0xfff2dc, 3.1);
  sun.position.copy(sunDirection).multiplyScalar(20);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -11, right: 11, top: 8, bottom: -8, near: 1, far: 50 });
  sun.shadow.bias = -0.00015;
  sun.shadow.normalBias = 0.02;
  scene.add(sun);
  const earthshine = new THREE.DirectionalLight(0x789bcf, 0.55);
  earthshine.position.set(-3, -4, 5);
  scene.add(earthshine);

  // A locally generated reflection environment supplies soft material highlights.
  const reflection = canvasTexture(512, 256, (ctx, width, height) => {
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, '#72839a');
    gradient.addColorStop(0.4, '#121b29');
    gradient.addColorStop(0.7, '#243f60');
    gradient.addColorStop(1, '#080e18');
    ctx.fillStyle = gradient; ctx.fillRect(0, 0, width, height);
    const glow = ctx.createRadialGradient(130, 70, 0, 130, 70, 75);
    glow.addColorStop(0, '#ffffff'); glow.addColorStop(0.1, '#e7d5b5'); glow.addColorStop(1, 'rgba(150,165,190,0)');
    ctx.fillStyle = glow; ctx.fillRect(55, 0, 150, 145);
  });
  reflection.mapping = THREE.EquirectangularReflectionMapping;
  const pmrem = new THREE.PMREMGenerator(renderer);
  let environment;
  function restoreEnvironment() {
    environment?.dispose();
    environment = pmrem.fromEquirectangular(reflection);
    scene.environment = environment.texture;
    scene.environmentIntensity = 0.65;
  }
  restoreEnvironment();

  // Half-float bloom is optional on devices without the required framebuffer support.
  let composer, bloom;
  if (renderer.extensions.has('EXT_color_buffer_float')) {
    // Avoid multisampled half-float targets: some WebGL drivers expose float
    // color buffers but resolve these targets to black. Pixel ratio supplies AA.
    const target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType });
    composer = new EffectComposer(renderer, target);
    composer.addPass(new RenderPass(scene, camera));
    bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.32, 0.5, 1.15);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());
  }
  const rand = randomGenerator(42);
  const starPositions = [], starColors = [];
  for (let i = 0; i < 1800; i++) {
    const phi = rand() * Math.PI * 2;
    const z = rand() * 2 - 1;
    const radius = 65 + rand() * 100;
    const k = Math.sqrt(1 - z * z);
    starPositions.push(radius * k * Math.cos(phi), radius * z, radius * k * Math.sin(phi));
    const brightness = 0.25 + rand() * 0.6;
    starColors.push(brightness * 0.72, brightness * 0.9, brightness);
  }
  const starGeometry = new THREE.BufferGeometry();
  starGeometry.setAttribute('position', new THREE.Float32BufferAttribute(starPositions, 3));
  starGeometry.setAttribute('color', new THREE.Float32BufferAttribute(starColors, 3));
  const starSprite = canvasTexture(64, 64, (ctx) => {
    const glow = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
    glow.addColorStop(0, '#ffffff'); glow.addColorStop(0.12, '#ffffff');
    glow.addColorStop(0.35, 'rgba(210,225,255,0.25)'); glow.addColorStop(1, 'rgba(200,220,255,0)');
    ctx.fillStyle = glow; ctx.fillRect(0, 0, 64, 64);
  });
  scene.add(new THREE.Points(starGeometry, new THREE.PointsMaterial({
    size: 0.28, vertexColors: true, sizeAttenuation: true, map: starSprite,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  })));

  // The guides are spatial overlays, not physical orbit predictions.
  const orbitGuides = [];
  for (const radius of [3.2, 5.1, 8.5]) {
    const points = Array.from({ length: 181 }, (_, i) => {
      const angle = i / 180 * Math.PI * 2;
      return v(Math.cos(angle) * radius, -0.45, Math.sin(angle) * radius);
    });
    const guide = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({
      color: 0x40768b, transparent: true, opacity: radius === 3.2 ? 0.35 : 0.16,
    }));
    guide.userData.opacity = guide.material.opacity;
    scene.add(guide);
    orbitGuides.push(guide);
  }

  const outbound = new THREE.CubicBezierCurve3(v(3.3, 0.6, 2), v(4.8, 1.3, 4.8), v(7.9, 2.3, 3.3), v(7.7, 1.6, -0.8));
  const returning = new THREE.CubicBezierCurve3(v(7.7, 1.6, -0.8), v(9, 0.4, -4), v(4.2, -0.3, -2), v(2.12, 0.5, 1.15));
  const makeTrack = (curve, color, dashed = false) => {
    const geometry = new THREE.BufferGeometry().setFromPoints(curve.getPoints(160));
    const material = dashed
      ? new THREE.LineDashedMaterial({ color, dashSize: 0.13, gapSize: 0.1, transparent: true, opacity: 0.4 })
      : new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.7 });
    const line = new THREE.Line(geometry, material);
    if (dashed) line.computeLineDistances();
    scene.add(line);
    return line;
  };
  const outTrack = makeTrack(outbound, 0x527e94, true);
  const planTrack = makeTrack(returning, CYAN, true);
  const flownTrack = makeTrack(returning, CYAN);

  const vehicle = createSpacecraft(textures);
  const { craft } = vehicle;
  craft.scale.setScalar(0.92);
  scene.add(craft);
  const landing = returning.getPoint(1);
  const landingBeacon = new THREE.Mesh(new THREE.SphereGeometry(0.055, 12, 8), new THREE.MeshBasicMaterial({ color: CYAN }));
  landingBeacon.position.copy(landing);
  const landingRing = new THREE.Mesh(new THREE.TorusGeometry(0.19, 0.007, 6, 48), new THREE.MeshBasicMaterial({ color: CYAN, transparent: true, opacity: 0.6 }));
  landingRing.position.copy(landing.clone().multiplyScalar(1.015));
  landingRing.lookAt(landing.clone().multiplyScalar(2));
  scene.add(landingBeacon, landingRing);
  const uncertainty = new THREE.Group();
  for (let axis = 0; axis < 3; axis++) {
    const circle = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(Array.from({ length: 96 }, (_, i) => {
      const a = i / 96 * Math.PI * 2;
      return v(Math.cos(a), Math.sin(a), 0);
    })), new THREE.LineBasicMaterial({ color: CYAN, transparent: true, opacity: 0.35 }));
    if (axis === 1) circle.rotation.x = Math.PI / 2;
    if (axis === 2) circle.rotation.y = Math.PI / 2;
    uncertainty.add(circle);
  }
  scene.add(uncertainty);
  const fixTargets = [v(-4, 7, -8), v(5, 6, -10), v(12, 1, -5), v(0, 0, 0), moon.position];
  const sightlines = fixTargets.map((target, i) => {
    const geometry = new THREE.BufferGeometry().setFromPoints([v(0, 0, 0), target]);
    const line = new THREE.Line(geometry, new THREE.LineDashedMaterial({ color: 0xe8c788, dashSize: 0.12, gapSize: 0.1, transparent: true, opacity: 0.5 }));
    scene.add(line);
    if (i < 3) {
      const beacon = new THREE.Mesh(new THREE.OctahedronGeometry(0.07), new THREE.MeshBasicMaterial({ color: 0xe8c788 }));
      beacon.position.copy(target);
      line.userData.beacon = beacon;
      scene.add(beacon);
    }
    return line;
  });

  let narrow = false;
  let viewWidth = 0;
  let viewHeight = 0;
  const labelEarth = document.querySelector('.earth-label');
  const labelCraft = document.querySelector('.craft-label');
  const projected = v(0, 0, 0);
  const attitude = new THREE.Matrix4();
  const origin = v(0, 0, 0);
  const up = v(0, 1, 0);
  const label = (element, position, offsetY = 0) => {
    projected.copy(position).project(camera);
    const width = viewWidth;
    const height = viewHeight;
    const x = (projected.x + 1) * width / 2;
    const y = (1 - projected.y) * height / 2 + offsetY;
    const visible = projected.z > -1 && projected.z < 1 && x > 20 && x < width - 140 && y > 80 && y < height - 200;
    element.style.transform = `translate(${x}px, ${y}px)`;
    element.style.opacity = visible ? '1' : '0';
  };

  function resize() {
    const bounds = canvas.parentElement.getBoundingClientRect();
    viewWidth = bounds.width;
    viewHeight = bounds.height;
    narrow = viewWidth < 760;
    camera.aspect = viewWidth / viewHeight;
    camera.fov = narrow ? 52 : 37;
    camera.updateProjectionMatrix();
    const pixelRatio = Math.min(window.devicePixelRatio || 1, narrow ? 1.25 : 1.75);
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(viewWidth, viewHeight, false);
    if (composer) {
      composer.setPixelRatio(pixelRatio);
      composer.setSize(viewWidth, viewHeight);
      bloom.strength = narrow ? 0.22 : 0.32;
    }
    sun.shadow.mapSize.set(narrow ? 1024 : 2048, narrow ? 1024 : 2048);
    if (sun.shadow.map && sun.shadow.map.width !== sun.shadow.mapSize.x) {
      sun.shadow.map.dispose(); sun.shadow.map = null;
    }
  }

  function render(time) {
    const state = missionState(time);
    const outK = ease(span(time, TIMING.coast, TIMING.fix));
    const backK = ease(span(time, TIMING.burn, TIMING.done));
    const curve = time < TIMING.burn ? outbound : returning;
    const progress = time < TIMING.burn ? outK : backK;
    craft.position.copy(curve.getPoint(progress));
    const direction = curve.getTangent(progress).normalize();
    // Reorient toward the return path before ignition; freeze at the same attitude when paused.
    if (time >= TIMING.plan && time < TIMING.burn) direction.lerp(returning.getTangent(0), ease(span(time, 22, 25.5))).normalize();
    craft.quaternion.setFromRotationMatrix(attitude.lookAt(direction, origin, up));
    craft.rotateZ(0.14 * Math.sin(time * 0.22));
    vehicle.update(time, state.burning, time >= TIMING.reentry && time < TIMING.done);
    craft.visible = time < TIMING.done;
    landingBeacon.visible = landingRing.visible = time >= TIMING.reentry;
    landingRing.scale.setScalar(1 + 0.3 * Math.sin(time * 2));

    planet.update(time);
    moon.rotation.y = time * 0.025;
    outTrack.geometry.setDrawRange(0, Math.max(0, Math.floor(outK * 160) + 1));
    outTrack.visible = time >= TIMING.coast;
    planTrack.geometry.setDrawRange(0, Math.floor(ease(span(time, TIMING.plan, TIMING.burn)) * 160) + 1);
    planTrack.visible = time >= TIMING.plan;
    flownTrack.geometry.setDrawRange(0, Math.floor(backK * 160) + 1);
    flownTrack.visible = time >= TIMING.burn;
    uncertainty.position.copy(craft.position);
    uncertainty.visible = time >= 6 && time < TIMING.plan;
    const spread = time < TIMING.fix ? span(time, 5, 14) : 1 - ease(span(time, 14, 22));
    uncertainty.scale.setScalar(0.35 + spread * 1.7);
    uncertainty.rotation.set(time * 0.08, time * 0.11, 0);
    sightlines.forEach((line, i) => {
      line.visible = time >= TIMING.fix + i * 0.8 && time < TIMING.plan;
      if (line.userData.beacon) line.userData.beacon.visible = line.visible;
      const attribute = line.geometry.attributes.position;
      attribute.setXYZ(0, craft.position.x, craft.position.y, craft.position.z);
      attribute.needsUpdate = true;
      line.geometry.computeBoundingSphere();
      if (line.visible) line.computeLineDistances();
    });

    const approach = ease(span(time, 32, 41));
    const orbit = Math.sin(time / TIMING.loop * Math.PI) * 0.7;
    const close = ease(span(time, 20, 26)) * (1 - ease(span(time, 29, 36)));
    const target = v(2.5 - approach, 1.5, 0);
    if (narrow) {
      const portrait = span(viewWidth / viewHeight, 0.75, 0.45);
      camera.position.set(-0.8 + orbit, 7.2 - approach, 24 + portrait * 5.5 - approach * 4);
      target.set(2.7 + portrait * 0.9 - approach * 1.8, 1.3, 0);
      // Move the scene into the space between the introduction and telemetry.
      camera.setViewOffset(viewWidth, viewHeight, 0, viewHeight * 0.025, viewWidth, viewHeight);
    } else {
      camera.clearViewOffset();
      const wide = v(-2 + orbit, 5.5 - approach, 24 - approach * 3);
      const closePosition = craft.position.clone().add(v(4.2, 2.4, 7.8));
      target.lerp(craft.position.clone().add(v(0.4, -0.25, 0)), close * 0.85);
      camera.position.copy(wide.lerp(closePosition, close * 0.85));
    }
    camera.lookAt(target);
    orbitGuides.forEach((guide) => { guide.material.opacity = guide.userData.opacity * (1 - close * 0.7); });
    if (composer) composer.render();
    else renderer.render(scene, camera);
    label(labelEarth, v(-0.6, -2.7, 0));
    label(labelCraft, craft.position, 48);
    labelCraft.style.opacity = craft.visible && !narrow ? labelCraft.style.opacity : '0';
  }

  resize();
  return { render, resize, restore: restoreEnvironment };
}
