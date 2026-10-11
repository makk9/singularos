import * as THREE from 'three';
import { TIMING, span, ease, missionState } from './mission.js';

const CYAN = 0x79f4ef;
const v = (x, y, z) => new THREE.Vector3(x, y, z);
const RADIUS = 2.45;

function randomGenerator(seed) {
  return () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
}

// Original, simplified continent outlines for the illustrative globe.
function earthTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#12374c';
  ctx.fillRect(0, 0, 1024, 512);
  const continents = [
    [[-168, 70], [-125, 73], [-98, 80], [-61, 53], [-52, 46], [-80, 25], [-87, 16], [-105, 21], [-118, 33], [-125, 49], [-151, 60]],
    [[-81, 12], [-60, 8], [-35, -6], [-41, -22], [-55, -35], [-68, -55], [-76, -40], [-80, -10]],
    [[-54, 83], [-20, 75], [-40, 59], [-60, 62]],
    [[-17, 35], [8, 37], [34, 31], [51, 12], [42, -14], [28, -35], [17, -34], [9, -5], [-14, 5]],
    [[-10, 36], [-10, 58], [7, 61], [19, 72], [36, 69], [48, 55], [33, 41], [16, 38]],
    [[30, 69], [70, 75], [110, 73], [160, 61], [178, 51], [142, 40], [130, 23], [109, 2], [100, 13], [80, 8], [70, 24], [47, 30], [37, 45]],
    [[113, -22], [131, -12], [151, -23], [153, -38], [130, -35], [114, -33]],
    [[47, -13], [51, -15], [48, -26], [44, -23]],
    [[129, 31], [142, 44], [145, 42], [136, 32]],
    [[166, -35], [179, -39], [170, -47], [164, -44]],
    [[-180, -73], [-100, -77], [-40, -69], [25, -72], [95, -69], [180, -75], [180, -90], [-180, -90]],
  ];
  ctx.fillStyle = '#40877f';
  ctx.strokeStyle = '#66b7a1';
  ctx.lineWidth = 1.2;
  for (const points of continents) {
    ctx.beginPath();
    points.forEach(([lon, lat], i) => {
      const x = (lon + 180) / 360 * 1024;
      const y = (90 - lat) / 180 * 512;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }
  const rand = randomGenerator(21);
  // A light surface grain keeps the globe tactile without external textures.
  for (let i = 0; i < 20000; i++) {
    ctx.fillStyle = rand() > 0.5 ? 'rgba(155,235,216,0.08)' : 'rgba(0,5,15,0.1)';
    ctx.fillRect(rand() * 1024, rand() * 512, 2, 2);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function atmosphere(radius, color, strength) {
  return new THREE.Mesh(new THREE.SphereGeometry(radius, 48, 32), new THREE.ShaderMaterial({
    uniforms: { tint: { value: new THREE.Color(color) }, strength: { value: strength } },
    vertexShader: `varying vec3 normalView; varying vec3 positionView;
      void main() {
        vec4 p = modelViewMatrix * vec4(position, 1.0);
        normalView = normalize(normalMatrix * normal);
        positionView = p.xyz;
        gl_Position = projectionMatrix * p;
      }`,
    fragmentShader: `uniform vec3 tint; uniform float strength;
      varying vec3 normalView; varying vec3 positionView;
      void main() {
        float rim = pow(1.0 - abs(dot(normalize(normalView), normalize(-positionView))), 3.0);
        gl_FragColor = vec4(tint, rim * strength);
      }`,
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
  }));
}

function spacecraft() {
  const craft = new THREE.Group();
  const hull = new THREE.MeshStandardMaterial({ color: 0xdce6e6, metalness: 0.65, roughness: 0.32 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x152a35, metalness: 0.7, roughness: 0.4 });
  const gold = new THREE.MeshStandardMaterial({ color: 0xc5a16b, metalness: 0.65, roughness: 0.35 });
  const glow = new THREE.MeshBasicMaterial({ color: CYAN });
  const add = (geometry, material, position = [0, 0, 0]) => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(...position);
    craft.add(mesh);
    return mesh;
  };
  const body = add(new THREE.CylinderGeometry(0.21, 0.27, 0.85, 8), hull);
  body.rotation.x = Math.PI / 2;
  const nose = add(new THREE.ConeGeometry(0.21, 0.36, 8), hull, [0, 0, 0.59]);
  nose.rotation.x = Math.PI / 2;
  add(new THREE.BoxGeometry(0.16, 0.07, 0.16), dark, [0, 0.18, 0.5]);
  for (const z of [-0.31, 0.25]) {
    const band = add(new THREE.CylinderGeometry(0.275, 0.275, 0.06, 8), gold, [0, 0, z]);
    band.rotation.x = Math.PI / 2;
  }
  const engine = add(new THREE.CylinderGeometry(0.17, 0.24, 0.22, 12, 1, true), dark, [0, 0, -0.52]);
  engine.rotation.x = Math.PI / 2;
  const throat = add(new THREE.CircleGeometry(0.13, 16), glow, [0, 0, -0.62]);
  throat.rotation.y = Math.PI;
  for (const side of [-1, 1]) {
    add(new THREE.BoxGeometry(1.5, 0.035, 0.05), gold, [side * 0.8, 0, 0]);
    const panel = add(new THREE.BoxGeometry(1.1, 0.72, 0.035), dark, [side * 1.07, 0, 0]);
    const solar = new THREE.MeshStandardMaterial({ color: 0x126b87, emissive: 0x063b4b, emissiveIntensity: 0.65, metalness: 0.55, roughness: 0.28 });
    add(new THREE.BoxGeometry(1.04, 0.66, 0.042), solar, [side * 1.07, 0, 0]);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(panel.geometry), new THREE.LineBasicMaterial({ color: 0x6ac9d6 }));
    edges.position.copy(panel.position);
    craft.add(edges);
    for (let i = 1; i < 6; i++) add(new THREE.BoxGeometry(0.012, 0.66, 0.052), gold, [side * 1.07 - 0.52 + i * 1.04 / 6, 0, 0]);
    for (let i = 1; i < 3; i++) add(new THREE.BoxGeometry(1.04, 0.01, 0.052), gold, [side * 1.07, -0.33 + i * 0.22, 0]);
  }
  add(new THREE.CylinderGeometry(0.012, 0.012, 0.5, 6), gold, [0, 0.5, -0.1]);
  add(new THREE.SphereGeometry(0.035, 8, 6), glow, [0, 0.77, -0.1]);
  const flame = add(new THREE.ConeGeometry(0.17, 1.5, 16, 1, true), new THREE.MeshBasicMaterial({
    color: CYAN, transparent: true, opacity: 0.6, depthWrite: false, blending: THREE.AdditiveBlending,
  }), [0, 0, -1.35]);
  flame.rotation.x = -Math.PI / 2;
  const core = add(new THREE.ConeGeometry(0.07, 1.1, 12), new THREE.MeshBasicMaterial({ color: 0xe5ffff }), [0, 0, -1.15]);
  core.rotation.x = -Math.PI / 2;
  const heat = atmosphere(0.62, 0xff704b, 0.7);
  craft.add(heat);
  return { craft, flame, core, heat };
}

export function createScene(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.3;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(37, 1, 0.1, 300);
  const earth = new THREE.Group();
  scene.add(earth);
  const globe = new THREE.Mesh(new THREE.SphereGeometry(RADIUS, 64, 36), new THREE.MeshStandardMaterial({
    map: earthTexture(), color: 0xc6e1df, roughness: 0.86, metalness: 0.15, flatShading: true,
  }));
  earth.add(globe);
  earth.add(atmosphere(RADIUS * 1.035, 0x53dce5, 0.65));
  earth.add(atmosphere(RADIUS * 1.12, 0x2b91c3, 0.18));
  const grid = new THREE.Mesh(new THREE.SphereGeometry(RADIUS * 1.006, 32, 16), new THREE.MeshBasicMaterial({
    color: CYAN, wireframe: true, transparent: true, opacity: 0.055, depthWrite: false,
  }));
  earth.add(grid);

  const rand = randomGenerator(42);
  const moonGeometry = new THREE.IcosahedronGeometry(0.65, 3);
  const moonPositions = moonGeometry.attributes.position;
  for (let i = 0; i < moonPositions.count; i++) {
    const p = v(moonPositions.getX(i), moonPositions.getY(i), moonPositions.getZ(i));
    // Coordinate-based relief keeps shared vertices together.
    p.multiplyScalar(1 + 0.025 * Math.sin(p.x * 18) * Math.cos(p.y * 23) * Math.sin(p.z * 16));
    moonPositions.setXYZ(i, p.x, p.y, p.z);
  }
  moonGeometry.computeVertexNormals();
  const moon = new THREE.Mesh(moonGeometry, new THREE.MeshStandardMaterial({ color: 0x819199, roughness: 1, flatShading: true }));
  moon.position.set(4, 3, -7);
  scene.add(moon);

  scene.add(new THREE.AmbientLight(0x49899e, 0.55));
  const sun = new THREE.DirectionalLight(0xe2f6ff, 3.3);
  sun.position.set(-5, 7, 6);
  scene.add(sun);
  const rim = new THREE.DirectionalLight(0x2ca8da, 2.5);
  rim.position.set(8, -2, -4);
  scene.add(rim);

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
  scene.add(new THREE.Points(starGeometry, new THREE.PointsMaterial({ size: 0.14, vertexColors: true, sizeAttenuation: true })));

  // The guides are spatial overlays, not physical orbit predictions.
  for (const radius of [3.2, 5.1, 8.5]) {
    const points = Array.from({ length: 181 }, (_, i) => {
      const angle = i / 180 * Math.PI * 2;
      return v(Math.cos(angle) * radius, -0.45, Math.sin(angle) * radius);
    });
    scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({
      color: 0x40768b, transparent: true, opacity: radius === 3.2 ? 0.35 : 0.16,
    })));
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

  const { craft, flame, core, heat } = spacecraft();
  craft.scale.setScalar(1.15);
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
    renderer.setSize(viewWidth, viewHeight, false);
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
    const burn = state.burning;
    flame.visible = core.visible = burn;
    const flicker = 1 + 0.12 * Math.sin(time * 73) + 0.06 * Math.sin(time * 117);
    flame.scale.set(1, flicker, 1);
    core.scale.set(1, flicker, 1);
    heat.visible = time >= TIMING.reentry && time < TIMING.done;
    heat.material.uniforms.strength.value = 0.6 + 0.2 * Math.sin(time * 24);
    craft.visible = time < TIMING.done;
    landingBeacon.visible = landingRing.visible = time >= TIMING.reentry;
    landingRing.scale.setScalar(1 + 0.3 * Math.sin(time * 2));

    globe.rotation.y = 2.3 + time * 0.008;
    grid.rotation.y = globe.rotation.y;
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

    const approach = ease(span(time, 29, 41));
    const orbit = Math.sin(time / TIMING.loop * Math.PI) * 0.9;
    const burnShot = ease(span(time, 21, 26)) * (1 - ease(span(time, 29, 37)));
    if (narrow) {
      camera.position.set(-1 + orbit, 8 - approach * 1.8, 31 - approach * 7);
      camera.lookAt(3.3 - approach * 2, 0.8, 0);
    } else {
      camera.position.set(-3 + orbit + approach * 2 + burnShot * 19, 5.5 - approach * 1.2, 17 - approach * 2.5 - burnShot * 3.5);
      camera.lookAt(2.9 - approach * 1.7 + burnShot * 2.5, 0.1, 0);
    }
    renderer.render(scene, camera);
    label(labelEarth, v(-0.6, -2.7, 0));
    label(labelCraft, craft.position, 48);
    labelCraft.style.opacity = craft.visible && !narrow ? labelCraft.style.opacity : '0';
  }

  resize();
  return { render, resize };
}
