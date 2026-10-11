import * as THREE from 'three';

export function randomGenerator(seed) {
  return () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
}

export function canvasTexture(width, height, draw, color = true) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  draw(canvas.getContext('2d'), width, height);
  const texture = new THREE.CanvasTexture(canvas);
  if (color) texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export function surfaceTextures() {
  const rand = randomGenerator(71);
  const foil = canvasTexture(256, 256, (ctx, width, height) => {
    ctx.fillStyle = '#aaa';
    ctx.fillRect(0, 0, width, height);
    for (let i = 0; i < 1700; i++) {
      const x = rand() * width, y = rand() * height;
      ctx.strokeStyle = `rgba(${rand() > 0.5 ? '255,255,255' : '0,0,0'},${0.08 + rand() * 0.2})`;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + rand() * 24 - 12, y + rand() * 32 - 16);
      ctx.stroke();
    }
  }, false);
  const solar = canvasTexture(512, 256, (ctx, width, height) => {
    ctx.fillStyle = '#060d21';
    ctx.fillRect(0, 0, width, height);
    for (let row = 0; row < 8; row++) for (let col = 0; col < 16; col++) {
      const x = col * 32 + 2, y = row * 32 + 2;
      const gradient = ctx.createLinearGradient(x, y, x + 30, y + 30);
      gradient.addColorStop(0, '#1d3d68');
      gradient.addColorStop(0.5, '#0d2145');
      gradient.addColorStop(1, '#264367');
      ctx.fillStyle = gradient;
      ctx.fillRect(x, y, 28, 28);
      ctx.fillStyle = '#8096a0';
      ctx.fillRect(x + 9, y, 0.7, 28);
      ctx.fillRect(x + 19, y, 0.7, 28);
      ctx.fillStyle = 'rgba(175,195,205,0.3)';
      for (let line = 1; line < 8; line++) ctx.fillRect(x, y + line * 3.5, 28, 0.4);
    }
  });
  const hull = canvasTexture(512, 256, (ctx, width, height) => {
    ctx.fillStyle = '#d4d9d8';
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = '#7c888e';
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 64) {
      ctx.strokeRect(x + 3, 4, 58, height - 8);
      ctx.fillStyle = '#68747d';
      for (const y of [11, height - 11]) for (const dx of [9, 55]) {
        ctx.beginPath(); ctx.arc(x + dx, y, 1.6, 0, Math.PI * 2); ctx.fill();
      }
    }
    ctx.fillStyle = '#303d48';
    ctx.font = 'bold 17px monospace';
    ctx.fillText('SINGULAR / 01', 80, 115);
    ctx.font = '9px monospace';
    ctx.fillText('AUTONOMOUS RECOVERY VEHICLE', 80, 136);
    ctx.fillStyle = '#a97339';
    ctx.fillRect(80, 150, 144, 3);
  });
  const moon = canvasTexture(1024, 512, (ctx, width, height) => {
    ctx.fillStyle = '#9b9d9f'; ctx.fillRect(0, 0, width, height);
    const crater = (x, y, radius) => {
      const gradient = ctx.createRadialGradient(x - radius * 0.2, y - radius * 0.2, 0, x, y, radius);
      gradient.addColorStop(0, '#656971');
      gradient.addColorStop(0.66, '#858890');
      gradient.addColorStop(0.83, '#c5c5c6');
      gradient.addColorStop(1, 'rgba(155,157,159,0)');
      ctx.fillStyle = gradient;
      ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
    };
    for (let i = 0; i < 42; i++) crater(rand() * width, rand() * height, 18 + rand() * 45);
    for (let i = 0; i < 1700; i++) {
      const x = rand() * width, y = rand() * height, radius = 1 + rand() * 9;
      // Repeat at the longitude seam to avoid a hard edge in the spherical map.
      for (const offset of [-width, 0, width]) crater(x + offset, y, radius);
    }
  }, false);
  return { foil, solar, hull, moon };
}
