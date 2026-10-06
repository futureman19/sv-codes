/* reveal.js — in-browser procedural reveal for SV-0002 collectibles.
   Port of poc/make_genesis_001.py reveal_params + render_reveal.
   Same (item, seed) -> same params -> structurally identical blade;
   rendering is per-engine (spec §7.2): pixels may differ from the issuer's
   canonical render, which the `art` hash pins. */
"use strict";
const SVReveal = (function () {

  const FORMS = ["long", "bastard", "katana", "claymore"];
  const EDGES = ["straight", "wave", "serrated"];
  const CORES = ["ember", "azure", "verdant", "umbral"];
  const GUARDS = ["swept", "straight", "claw"];
  const HALF_W = { long: 46, bastard: 54, katana: 34, claymore: 62 };
  const CORE_RGB = { ember: [255, 122, 40], azure: [90, 170, 255],
                     verdant: [90, 220, 140], umbral: [170, 110, 230] };

  function hexBytes(hex) {
    const out = new Uint8Array(hex.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
    return out;
  }

  /* MUST match make_genesis_001.reveal_params exactly */
  function params(seedHex) {
    const b = SVC.sha256(hexBytes(seedHex));           // deterministic expansion
    return {
      form: FORMS[b[0] % FORMS.length],
      edge: EDGES[b[1] % EDGES.length],
      core: CORES[b[2] % CORES.length],
      guard: GUARDS[(b[0] ^ b[1]) % GUARDS.length],
      length: 0.55 + (b[3] / 255) * 0.17,
      glow: 0.55 + (b[4] / 255) * 0.40,
    };
  }

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function renderGenesisBlade(canvas, seedHex) {
    const p = params(seedHex);
    const S = canvas.width / 1024;                      // all coords in 1024-space
    const ctx = canvas.getContext("2d");
    const rgba = (c, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

    ctx.fillStyle = "#090b14";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    // starfield (decor — per-engine PRNG, not part of the canonical hash)
    const rng = mulberry32(parseInt(seedHex, 16));
    for (let i = 0; i < 180; i++) {
      const v = 60 + Math.floor(rng() * 140);
      ctx.fillStyle = `rgb(${v},${v},${Math.min(255, v + 30)})`;
      ctx.fillRect(rng() * canvas.width, rng() * canvas.height, 1, 1);
    }

    const cx = 512, top = 1024 * 0.08;
    const bladeLen = 1024 * p.length, baseY = top + bladeLen;
    const halfW = HALF_W[p.form];
    const core = CORE_RGB[p.core];

    const edge = (t) => {
      let w = halfW * Math.pow(t, 0.85);
      const xoff = p.form === "katana" ? cx - 26 * Math.sin(t * Math.PI) : cx;
      if (p.edge === "wave") w *= 1 + 0.16 * Math.sin(t * 22);
      return [xoff, w];
    };
    const N = 65, ptsL = [], ptsR = [];
    for (let i = 0; i < N; i++) {
      const t = i / 64;
      let [xoff, w] = edge(t);
      if (p.edge === "serrated") w *= 1 + (i % 6 < 3 ? 0.22 : -0.10);
      const y = top + t * bladeLen;
      ptsL.push([xoff - w, y]); ptsR.push([xoff + w, y]);
    }
    const path = (pts) => {
      ctx.beginPath();
      ctx.moveTo(pts[0][0] * S, pts[0][1] * S);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0] * S, pts[i][1] * S);
    };
    // blade body
    path(ptsL.concat(ptsR.slice().reverse()));
    ctx.closePath();
    ctx.fillStyle = rgba([148, 158, 178]);
    ctx.fill();
    // brushed shading + fuller
    ctx.lineWidth = Math.max(1, 1 * S);
    for (let i = 1; i < 64; i += 2) {
      const t = i / 64, [xoff, w] = edge(t), y = (top + t * bladeLen) * S;
      ctx.strokeStyle = rgba([128, 138, 158]);
      ctx.beginPath(); ctx.moveTo((xoff - w) * S, y); ctx.lineTo((xoff + w) * S, y); ctx.stroke();
    }
    for (let i = 6; i < 60; i++) {
      const t = i / 64, [xoff] = edge(t), y = (top + t * bladeLen) * S;
      ctx.strokeStyle = rgba([108, 118, 140]);
      ctx.beginPath(); ctx.moveTo((xoff - 3) * S, y); ctx.lineTo((xoff + 3) * S, y); ctx.stroke();
    }
    // bright bevels
    ctx.strokeStyle = rgba([212, 220, 236]);
    ctx.lineWidth = 3 * S;
    path(ptsL); ctx.stroke();
    path(ptsR); ctx.stroke();
    // core glow: halo + solid channel
    ctx.save();
    ctx.filter = `blur(${10 * S}px)`;
    for (let i = 10; i < 58; i++) {
      const t = i / 64, [xoff] = edge(t), y = top + t * bladeLen;
      ctx.fillStyle = rgba(core, 0.59 * p.glow);
      ctx.beginPath();
      ctx.ellipse(xoff * S, y * S, 14 * S, 14 * S, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
    ctx.strokeStyle = rgba(core, 0.90 * p.glow);
    ctx.lineWidth = 4 * S;
    ctx.beginPath();
    for (let i = 10; i < 58; i++) {
      const t = i / 64, [xoff] = edge(t), y = (top + t * bladeLen) * S;
      if (i === 10) ctx.moveTo(xoff * S, y); else ctx.lineTo(xoff * S, y);
    }
    ctx.stroke();

    // guard
    const gy = baseY, gw = { straight: 150, swept: 190, claw: 130 }[p.guard];
    ctx.fillStyle = rgba([70, 58, 40]);
    if (p.guard === "swept") {
      path([[cx - 8, gy], [cx + 8, gy], [cx + gw, gy - 26], [cx + gw, gy - 12]]); ctx.closePath(); ctx.fill();
      path([[cx - 8, gy], [cx + 8, gy], [cx - gw, gy - 26], [cx - gw, gy - 12]]); ctx.closePath(); ctx.fill();
    } else if (p.guard === "claw") {
      ctx.fillRect((cx - gw) * S, (gy - 8) * S, 2 * gw * S, 12 * S);
      path([[cx - gw, gy - 8], [cx - gw + 26, gy - 34], [cx - gw + 40, gy - 8]]); ctx.closePath(); ctx.fill();
      path([[cx + gw, gy - 8], [cx + gw - 26, gy - 34], [cx + gw - 40, gy - 8]]); ctx.closePath(); ctx.fill();
    } else {
      ctx.fillRect((cx - gw) * S, (gy - 6) * S, 2 * gw * S, 12 * S);
    }
    ctx.fillStyle = rgba([120, 100, 66]);
    ctx.fillRect((cx - gw) * S, (gy - 2) * S, 2 * gw * S, 4 * S);
    // grip + pommel
    ctx.fillStyle = rgba([34, 30, 34]);
    ctx.fillRect((cx - 12) * S, (gy + 8) * S, 24 * S, 88 * S);
    ctx.strokeStyle = rgba([58, 50, 52]);
    ctx.lineWidth = Math.max(1, 1 * S);
    for (let y = gy + 12; y < gy + 96; y += 8) {
      ctx.beginPath(); ctx.moveTo((cx - 12) * S, y * S); ctx.lineTo((cx + 12) * S, y * S); ctx.stroke();
    }
    ctx.fillStyle = rgba([70, 58, 40]);
    ctx.beginPath(); ctx.ellipse(cx * S, (gy + 115) * S, 22 * S, 19 * S, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = rgba(core);
    ctx.beginPath(); ctx.ellipse(cx * S, (gy + 117) * S, 10 * S, 9 * S, 0, 0, Math.PI * 2); ctx.fill();
    return p;
  }

  const GENERATORS = { "genesis-blade": renderGenesisBlade };

  function render(canvas, item, seedHex) {
    const g = GENERATORS[item];
    return g ? g(canvas, seedHex) : null;
  }

  return { params, render, GENERATORS };
})();
if (typeof module !== "undefined") module.exports = SVReveal;
