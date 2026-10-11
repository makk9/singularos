(() => {
  const C = {
    deep: "#123a6b",
    ink: "#0d2c52",
    paper: "#dce9f5",
    line: "#6f93bd",
    signal: "#ff8a3d",
    sight: "#f2d27a",
  };

  // Phase boundaries in seconds of loop time.
  const T = { boot: 0, coast: 5, fix: 14, plan: 22, burn: 26, reentry: 37, done: 41, loop: 46 };
  const PHASES = ["boot", "coast", "fix", "plan", "burn", "reentry"];

  // Simulated minutes per real second, for the mission clock.
  const MET_SCALE = 20;

  const LOG = [
    [0.3, "Booted on unknown hardware. Probing devices."],
    [1.6, "Found 1 camera, 1 IMU, 2 reaction wheels, 1 thruster."],
    [3.0, "No GPS lock. Ground link silent."],
    [4.3, "Switching to self-navigation."],
    [6.0, "Coasting. Tracking motion with the IMU only."],
    [10.0, "Drift is growing. Position estimate degrading."],
    [14.3, "Pointing camera at the sky. Matching star patterns."],
    [16.5, "Matched 3 stars against the onboard catalog."],
    [18.5, "Sighted Earth and Moon. Triangulating."],
    [21.0, "Position fixed to within 1.2 km."],
    [22.5, "Plotting a return trajectory."],
    [25.0, "Trajectory found. Burn in 1 s."],
    [26.2, "Main burn started."],
    [28.5, "Burn complete. Coasting toward Earth."],
    [37.2, "Entering atmosphere."],
    [40.5, "Splashdown. Mission complete."],
  ];

  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  const logEl = document.getElementById("log");
  const metEl = document.getElementById("met");
  const errEl = document.getElementById("err");
  const phaseEls = [...document.querySelectorAll("#phases li")];
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  let W = 0, H = 0, S = 0, G = {};
  let stars = [];

  // Deterministic star field so it is stable across resizes.
  function rng(seed) {
    return () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 4294967296;
    };
  }

  function layout() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth;
    H = window.innerHeight;
    S = Math.min(W, H);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const narrow = W < 720;
    const E = { x: W * (narrow ? 0.3 : 0.36), y: H * (narrow ? 0.52 : 0.58) };
    const r = S * 0.065;
    const F = { x: W * (narrow ? 0.78 : 0.7), y: H * (narrow ? 0.4 : 0.44) };
    const L = { x: E.x + r * Math.cos(-0.5), y: E.y + r * Math.sin(-0.5) };
    const R = { x: E.x + r * Math.cos(0.7), y: E.y + r * Math.sin(0.7) };

    G = {
      E, r, F, L, R,
      moonOrbit: S * 0.24,
      out: [L, { x: W * 0.5, y: H * 0.14 }, F],
      back: [F, { x: W * 0.82, y: H * 0.86 }, { x: E.x + S * 0.32, y: E.y + S * 0.3 }, R],
      nav: [
        { x: W * 0.08, y: H * 0.7 },
        { x: W * 0.58, y: H * 0.1 },
        { x: W * 0.95, y: H * 0.72 },
      ],
    };

    const rand = rng(7);
    stars = Array.from({ length: Math.round((W * H) / 5200) }, () => ({
      x: rand() * W,
      y: rand() * H,
      s: rand() < 0.08 ? 1.4 : 0.7,
      a: 0.25 + rand() * 0.5,
    }));
  }

  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
  const span = (t, a, b) => clamp((t - a) / (b - a));

  function quad([p0, p1, p2], t) {
    const u = 1 - t;
    return {
      x: u * u * p0.x + 2 * u * t * p1.x + t * t * p2.x,
      y: u * u * p0.y + 2 * u * t * p1.y + t * t * p2.y,
    };
  }

  function cubic([p0, p1, p2, p3], t) {
    const u = 1 - t;
    return {
      x: u * u * u * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t * t * t * p3.x,
      y: u * u * u * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t * t * t * p3.y,
    };
  }

  function strokePath(fn, pts, t0, t1, steps = 80) {
    ctx.beginPath();
    for (let i = 0; i <= steps; i++) {
      const p = fn(pts, t0 + (t1 - t0) * (i / steps));
      i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();
  }

  function drawGrid() {
    ctx.strokeStyle = "rgba(111,147,189,0.14)";
    ctx.lineWidth = 1;
    const step = S * 0.08;
    ctx.beginPath();
    for (let x = G.E.x % step; x < W; x += step) { ctx.moveTo(x, 0); ctx.lineTo(x, H); }
    for (let y = G.E.y % step; y < H; y += step) { ctx.moveTo(0, y); ctx.lineTo(W, y); }
    ctx.stroke();

    ctx.setLineDash([2, 6]);
    ctx.strokeStyle = "rgba(111,147,189,0.45)";
    ctx.fillStyle = "rgba(111,147,189,0.8)";
    ctx.font = "11px 'Atkinson Hyperlegible', sans-serif";
    [0.24, 0.42, 0.6].forEach((k, i) => {
      ctx.beginPath();
      ctx.arc(G.E.x, G.E.y, S * k, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillText(`${[384, 672, 960][i]},000 km`, G.E.x + 4, G.E.y - S * k - 4);
    });
    ctx.setLineDash([]);
  }

  function drawStars(t) {
    for (const s of stars) {
      ctx.fillStyle = `rgba(220,233,245,${s.a})`;
      ctx.fillRect(s.x, s.y, s.s, s.s);
    }
    const lit = t >= T.fix && t < T.plan + 1;
    G.nav.forEach((p) => {
      ctx.fillStyle = lit ? C.sight : C.paper;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = lit ? C.sight : "rgba(220,233,245,0.5)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(p.x - 7, p.y); ctx.lineTo(p.x + 7, p.y);
      ctx.moveTo(p.x, p.y - 7); ctx.lineTo(p.x, p.y + 7);
      ctx.stroke();
    });
  }

  function moonPos(t) {
    const a = -1.1 + t * 0.012;
    return { x: G.E.x + Math.cos(a) * G.moonOrbit, y: G.E.y + Math.sin(a) * G.moonOrbit };
  }

  function drawEarth(t) {
    const { E, r } = G;
    const glow = t >= T.reentry ? Math.sin(span(t, T.reentry, T.done) * Math.PI) : 0;
    if (glow > 0) {
      ctx.strokeStyle = `rgba(255,138,61,${0.6 * glow})`;
      ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.arc(E.x, E.y, r + 6, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.fillStyle = C.ink;
    ctx.strokeStyle = C.paper;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(E.x, E.y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.save();
    ctx.clip();
    ctx.strokeStyle = "rgba(220,233,245,0.35)";
    ctx.lineWidth = 1;
    const spin = (t * 0.15) % 1;
    for (let i = 0; i < 4; i++) {
      const k = Math.cos(((i + spin) / 4) * Math.PI);
      ctx.beginPath();
      ctx.ellipse(E.x, E.y, Math.abs(k) * r, r, 0, 0, Math.PI * 2);
      ctx.stroke();
    }
    [-0.5, 0, 0.5].forEach((k) => {
      ctx.beginPath();
      ctx.moveTo(E.x - r, E.y + k * r);
      ctx.lineTo(E.x + r, E.y + k * r);
      ctx.stroke();
    });
    ctx.restore();

    const m = moonPos(t);
    ctx.fillStyle = C.deep;
    ctx.strokeStyle = C.paper;
    ctx.beginPath();
    ctx.arc(m.x, m.y, r * 0.27, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }

  function craftState(t) {
    if (t < T.coast) return { p: G.L, d: quad(G.out, 0.01) };
    if (t < T.burn) {
      const k = ease(span(t, T.coast, T.fix)) * 1;
      return { p: quad(G.out, k), d: quad(G.out, Math.min(1, k + 0.01)), outK: k };
    }
    const k = Math.pow(span(t, T.burn, T.done), 1.15);
    return { p: cubic(G.back, k), d: cubic(G.back, Math.min(1, k + 0.01)), backK: k };
  }

  function drawCraft(t, st) {
    const { p, d } = st;
    const ang = Math.atan2(d.y - p.y, d.x - p.x) || 0;
    const burning = t >= T.burn && t < T.burn + 2.3;
    const blink = t < T.coast ? (Math.floor(t * 3) % 2 === 0) : true;
    if (!blink) return;
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(ang);
    if (burning) {
      const f = 10 + Math.random() * 6;
      ctx.fillStyle = C.sight;
      ctx.beginPath();
      ctx.moveTo(-5, -3); ctx.lineTo(-5 - f, 0); ctx.lineTo(-5, 3);
      ctx.fill();
    }
    ctx.fillStyle = C.signal;
    ctx.beginPath();
    ctx.moveTo(8, 0); ctx.lineTo(-6, -5); ctx.lineTo(-3, 0); ctx.lineTo(-6, 5);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function uncertainty(t) {
    if (t < T.coast) return 0;
    if (t < T.fix) return S * 0.2 * ease(span(t, T.coast, T.fix));
    if (t < T.plan) return S * 0.2 * (1 - ease(span(t, T.fix + 1, T.plan - 0.8))) + 4 * ease(span(t, T.fix, T.plan));
    return 0;
  }

  function errKm(t) {
    if (t < T.coast) return null;
    if (t < T.fix) return 50 + 411950 * ease(span(t, T.coast, T.fix));
    if (t < T.plan) {
      const k = ease(span(t, T.fix + 1, T.plan - 0.8));
      return Math.max(1.2, 412000 * Math.pow(1 - k, 3));
    }
    return 1.2;
  }

  function draw(t) {
    ctx.clearRect(0, 0, W, H);
    drawGrid();
    drawStars(t);
    drawEarth(t);

    const st = craftState(t);

    // Outbound track: dashed, the craft did not know where it was.
    if (t >= T.coast) {
      ctx.setLineDash([3, 5]);
      ctx.strokeStyle = "rgba(220,233,245,0.45)";
      ctx.lineWidth = 1.2;
      strokePath(quad, G.out, 0, t < T.burn ? st.outK : 1);
      ctx.setLineDash([]);
    }

    // Planned return path drawn in during the plan phase.
    if (t >= T.plan) {
      const k = ease(span(t, T.plan, T.burn - 0.5));
      ctx.setLineDash([8, 6]);
      ctx.strokeStyle = "rgba(255,138,61,0.55)";
      ctx.lineWidth = 1.5;
      strokePath(cubic, G.back, 0, k);
      ctx.setLineDash([]);
    }

    // Flown return track.
    if (t >= T.burn) {
      ctx.strokeStyle = C.signal;
      ctx.lineWidth = 2;
      strokePath(cubic, G.back, 0, st.backK);
    }

    // Sightlines from the craft to stars, Earth, and Moon during the fix.
    if (t >= T.fix && t < T.plan + 0.6) {
      const targets = [...G.nav, G.E, moonPos(t)];
      targets.forEach((q, i) => {
        const k = clamp((t - T.fix - i * 0.9) / 1.2);
        if (k <= 0) return;
        const fade = t > T.plan ? 1 - span(t, T.plan, T.plan + 0.6) : 1;
        ctx.strokeStyle = `rgba(242,210,122,${0.75 * fade})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(st.p.x, st.p.y);
        ctx.lineTo(st.p.x + (q.x - st.p.x) * k, st.p.y + (q.y - st.p.y) * k);
        ctx.stroke();
      });
    }

    // Position uncertainty ring.
    const u = uncertainty(t);
    if (u > 0.5) {
      const locked = t >= T.fix;
      ctx.strokeStyle = locked ? C.sight : C.paper;
      ctx.fillStyle = locked ? "rgba(242,210,122,0.08)" : "rgba(220,233,245,0.06)";
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.arc(st.p.x, st.p.y, u, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }

    drawCraft(t, st);

    if (t >= T.done - 0.5) {
      ctx.fillStyle = C.paper;
      ctx.font = "700 14px 'Atkinson Hyperlegible', sans-serif";
      ctx.fillText("Splashdown", G.R.x + 12, G.R.y + 16);
    }
  }

  function fmtMet(t) {
    const m = Math.floor(t * MET_SCALE);
    return `T+${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  }

  let shown = -1;
  function updateUI(t) {
    metEl.textContent = fmtMet(Math.min(t, T.done));

    const e = errKm(t);
    errEl.textContent = e === null ? "no fix" : e >= 10 ? `${Math.round(e).toLocaleString("en-US")} km` : `${e.toFixed(1)} km`;
    errEl.classList.toggle("locked", t >= T.plan - 1);

    let n = 0;
    while (n < LOG.length && LOG[n][0] <= t) n++;
    if (n !== shown) {
      shown = n;
      logEl.replaceChildren(
        ...LOG.slice(Math.max(0, n - 5), n).map(([at, text]) => {
          const li = document.createElement("li");
          const time = document.createElement("time");
          time.textContent = fmtMet(at);
          li.append(time, text);
          return li;
        })
      );
    }

    const bounds = PHASES.map((p) => T[p]).concat(T.done);
    phaseEls.forEach((el, i) => {
      const active = t >= bounds[i] && t < bounds[i + 1];
      el.classList.toggle("active", active);
      el.classList.toggle("done", t >= bounds[i + 1]);
      if (active) el.setAttribute("aria-current", "step");
      else el.removeAttribute("aria-current");
    });
  }

  let start = performance.now();
  function frame(now) {
    const t = ((now - start) / 1000) % T.loop;
    draw(t);
    updateUI(t);
    if (!reduceMotion.matches) requestAnimationFrame(frame);
  }

  function renderStill() {
    const t = T.burn - 0.5;
    draw(t);
    updateUI(t);
  }

  // ?t=<seconds> freezes the loop at that moment.
  const frozen = parseFloat(new URLSearchParams(location.search).get("t"));

  function run() {
    layout();
    if (!Number.isNaN(frozen)) { draw(frozen); updateUI(frozen); }
    else if (reduceMotion.matches) renderStill();
    else { start = performance.now(); requestAnimationFrame(frame); }
  }

  window.addEventListener("resize", () => {
    layout();
    if (!Number.isNaN(frozen)) { draw(frozen); updateUI(frozen); }
    else if (reduceMotion.matches) renderStill();
  });
  reduceMotion.addEventListener("change", run);

  layout();
  document.fonts.ready.then(run);
})();
