/* decoder.js — SV-0001 §6 receiver pipeline in pure JS (no OpenCV):
   HSV anchor masking -> centroids -> homography -> majority-vote binarize
   -> frame parse -> LT solve -> CRC32 -> BMP envelope parse + ECDSA verify.

   Verified bit-exact against the Python reference via poc/fixtures/. */
"use strict";
const SVDec = (() => {
const S = (typeof module !== "undefined") ? require("./svc.js") : SVC;

/* RGB -> HSV (OpenCV scale: H 0-179, S/V 0-255). Returns hue class or -1. */
function classify(r, g, b){
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const d = max - min;
  if (d * 255 < 204 * max) return -1;          // S < 204/255 -> not anchor (matches Python)
  if (max < 204) return -1;                    // V < 80%
  let h;
  if (max === r)      h = 30 * (((g - b) / d) % 6);
  else if (max === g) h = 30 * ((b - r) / d + 2);
  else                h = 30 * ((r - g) / d + 4);
  if (h < 0) h += 180;
  if (h >= 75 && h <= 105)  return 0;          // TL cyan (liberal: survives night-light shift)
  if (h >= 135 && h <= 165) return 1;          // TR magenta
  if (h >= 20 && h <= 40)   return 2;          // BL yellow
  if (h <= 8 || h >= 172)   return 3;          // BR red
  return -1;
}

/* Find anchor centroids + hue-mask areas in RGBA image data.
   Areas are rotation-invariant, so they give the cell pitch even for
   rotated grids — that is how the grid size (64 vs 96) is inferred. */
function anchorStats(data, width, height){
  const sumX = [0,0,0,0], sumY = [0,0,0,0], cnt = [0,0,0,0];
  const step = 2;                              // sample every 2nd pixel for speed
  for (let y = 0; y < height; y += step){
    const row = y * width * 4;
    for (let x = 0; x < width; x += step){
      const i = row + x * 4;
      const cls = classify(data[i], data[i+1], data[i+2]);
      if (cls >= 0){ cnt[cls]++; sumX[cls] += x; sumY[cls] += y; }
    }
  }
  const minArea = Math.max(12, (width * height) / (step * step) * 0.00005);
  const pts = [], areas = [];
  for (let c = 0; c < 4; c++){
    if (cnt[c] < minArea) return null;
    pts.push([sumX[c] / cnt[c], sumY[c] / cnt[c]]);
    areas.push(cnt[c] * step * step);
  }
  return {pts, areas};
}

/* Find anchor centroids in RGBA image data. Returns [tl,tr,bl,br] or null. */
function findAnchors(data, width, height){
  const s = anchorStats(data, width, height);
  return s ? s.pts : null;
}

/* Grid configurations: SV-0001 (64) and SV-0005 QR-inlay (96). */
const GRIDS = {
  64: { GRID: 64, INNER: 52, OFFSET: 6, FRAME_BITS: 2704, inlay: null },
  96: { GRID: 96, INNER: 84, OFFSET: 6, FRAME_BITS: 40 + 24 * 256,
        inlay: { cells: 29, origin: 27 } },   // canonical SV-0005 inlay
};
function gridFor(areas, pts){
  let pitch = 0;
  for (const a of areas) pitch += Math.sqrt(a / 16);   // anchor = 4x4 cells
  pitch /= 4;
  if (!(pitch > 0)) return null;
  const spanX = Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]);
  const spanY = Math.hypot(pts[2][0] - pts[0][0], pts[2][1] - pts[0][1]);
  const est = ((spanX + spanY) / 2) / pitch + 4;       // span = (GRID-4)*pitch
  let best = null, bd = 1e9;
  for (const g of [64, 96]){ const d = Math.abs(est - g); if (d < bd){ bd = d; best = g; } }
  return bd <= 6 ? GRIDS[best] : null;
}
/* Confidence-scored grid selection: sample the frame under BOTH candidate
   grids and keep the one whose cell means are more bipolar. The true grid
   lands each sample inside one printed cell (means near the rails); the
   wrong grid straddles cells (means mid-gray). Immune to anchor shape art
   (circular gem anchors defeat area-based pitch estimates). */
function gridConfidence(means){
  let mLo = 255, mHi = 0;
  for (const m of means){ if (m < mLo) mLo = m; if (m > mHi) mHi = m; }
  const span = mHi - mLo;
  if (span < 40) return {conf: -1, mLo, mHi};          // no contrast
  const theta = (mLo + mHi) / 2;
  let acc = 0;
  for (const m of means) acc += Math.min(1, Math.abs(m - theta) / (0.25 * span));
  return {conf: acc / means.length, mLo, mHi};
}

/* 4-point homography (DLT, h33 = 1): canonical cell coords -> image pixels */
function solveHomography(src, dst){
  // src/dst: [[x,y] x4] order tl,tr,bl,br
  const A = [], Bv = [];
  for (let i = 0; i < 4; i++){
    const [x, y] = src[i], [X, Y] = dst[i];
    A.push([x, y, 1, 0, 0, 0, -X*x, -X*y]); Bv.push(X);
    A.push([0, 0, 0, x, y, 1, -Y*x, -Y*y]); Bv.push(Y);
  }
  // Gaussian elimination with partial pivoting
  const n = 8;
  for (let col = 0; col < n; col++){
    let piv = col;
    for (let r = col+1; r < n; r++) if (Math.abs(A[r][col]) > Math.abs(A[piv][col])) piv = r;
    if (Math.abs(A[piv][col]) < 1e-12) return null;
    [A[col], A[piv]] = [A[piv], A[col]]; [Bv[col], Bv[piv]] = [Bv[piv], Bv[col]];
    for (let r = 0; r < n; r++){
      if (r === col) continue;
      const f = A[r][col] / A[col][col];
      for (let c = col; c < n; c++) A[r][c] -= f * A[col][c];
      Bv[r] -= f * Bv[col];
    }
  }
  const h = new Array(8);
  for (let i = 0; i < n; i++) h[i] = Bv[i] / A[i][i];
  return h;
}
function applyH(h, x, y){
  const w = h[6]*x + h[7]*y + 1;
  return [(h[0]*x + h[1]*y + h[2]) / w, (h[3]*x + h[4]*y + h[5]) / w];
}

function gray(data, width, x, y){
  const xi = Math.round(x), yi = Math.round(y);
  const height = data.length / (4 * width);
  if (xi < 0 || yi < 0 || xi >= width || yi >= height) return 255;
  const i = (yi * width + xi) * 4;
  return 0.299*data[i] + 0.587*data[i+1] + 0.114*data[i+2];
}

/* Full frame decode: RGBA data -> payload bits (2,704 for SV-0001 grids,
   6,184 for SV-0005 inlay grids), or null. Grid size is inferred from the
   anchor pitch; inlay cells are skipped per the canonical SV-0005 layout. */
function decodeImageData(data, width, height){
  const st = anchorStats(data, width, height);
  if (!st) return null;

  // block-averaged sampling (4x4 sub-samples, central 50% of each cell)
  const SUB = [-0.225, -0.075, 0.075, 0.225];
  function sampleCells(cfg){
    const canonical = [[2,2],[cfg.GRID-2,2],[2,cfg.GRID-2],[cfg.GRID-2,cfg.GRID-2]];
    const H = solveHomography(canonical, st.pts);
    if (!H) return null;
    const cells = [];
    if (!cfg.inlay){
      for (let i = 0; i < cfg.FRAME_BITS; i++)
        cells.push([cfg.OFFSET + Math.floor(i / cfg.INNER), cfg.OFFSET + (i % cfg.INNER)]);
    } else {
      const o = cfg.inlay.origin, n = cfg.inlay.cells;
      outer: for (let r = 0; r < cfg.INNER; r++){
        for (let c = 0; c < cfg.INNER; c++){
          if (r >= o && r < o + n && c >= o && c < o + n) continue;
          cells.push([cfg.OFFSET + r, cfg.OFFSET + c]);
          if (cells.length === cfg.FRAME_BITS) break outer;
        }
      }
    }
    const means = new Float32Array(cells.length);
    for (let i = 0; i < cells.length; i++){
      const [r, c] = cells[i];
      let acc = 0;
      for (const dy of SUB) for (const dx of SUB){
        const [X, Y] = applyH(H, c + 0.5 + dx, r + 0.5 + dy);
        acc += gray(data, width, X, Y);
      }
      means[i] = acc / 16;
    }
    return means;
  }

  // try both grids; the true one reads near the rails (midpoint-of-extremes
  // threshold — Otsu splits multi-modal art and is banned by the format contract)
  let best = null;
  for (const g of [64, 96]){
    const cfg = GRIDS[g];
    const means = sampleCells(cfg);
    if (!means) continue;
    const {conf, mLo, mHi} = gridConfidence(means);
    if (best && conf <= best.conf) continue;
    best = {conf, means, mLo, mHi, n: means.length};
  }
  if (!best || best.conf < 0.6) return null;
  const thetaB = (best.mLo + best.mHi) / 2;
  const bits = new Uint8Array(best.n);
  for (let i = 0; i < best.n; i++) bits[i] = best.means[i] < thetaB ? 1 : 0;
  return bits;
}

/* Stream decoder: accumulate frames -> envelope. verify via authority pubkey(s). */
class StreamScanner {
  constructor(authorityPubHex){
    this.lts = new Map();                      // K -> LTDecoder
    // accepts one hex string or an array of them (issuer registry)
    const pubs = Array.isArray(authorityPubHex) ? authorityPubHex
               : authorityPubHex ? [authorityPubHex] : [];
    this.authorities = pubs.map(p => ({hex: p, Q: S.parsePubkey(p)}));
    this.framesSeen = 0;
    this.lastK = null;
  }
  feedBits(bits){
    const {seed, ctype, K, symbols} = S.unpackFrameAuto(bits);
    this.framesSeen++; this.lastK = K;
    if (!this.lts.has(K)) this.lts.set(K, new S.LTDecoder(K));
    const lt = this.lts.get(K);
    for (let slot = 0; slot < symbols.length; slot++){
      const sym = symbols[slot];
      if (sym.every(b => b === 0)) continue;
      if (lt.add(seed, slot, sym)){
        const solved = lt.solved();
        if (!solved) continue;
        const buf = concatBytes(solved);
        let content;
        try { content = S.parseStream(buf); }
        catch (e) { this.lts.delete(K); return null; }  // mixed streams: reset K
        const env = S.parseEnvelope(content);
        let sig, issuer = null;
        if (env.signature.every(b => b === 0)) sig = "demo";
        else if (this.authorities.length){
          const digest = S.envelopeDigest(content);
          sig = "invalid";
          for (const a of this.authorities){
            if (S.ecdsaVerify(a.Q, env.signature, digest)){ sig = "valid"; issuer = a.hex; break; }
          }
        }
        else sig = "unverified";
        return {env, ctype, sig, issuer};
      }
    }
    return null;
  }
  progress(){
    if (this.lastK === null || !this.lts.has(this.lastK)) return null;
    return [this.lts.get(this.lastK).count(), this.lastK];
  }
}
function concatBytes(arrs){
  let n = 0; for (const a of arrs) n += a.length;
  const out = new Uint8Array(n); let o = 0;
  for (const a of arrs){ out.set(a, o); o += a.length; }
  return out;
}

return { classify, findAnchors, anchorStats, gridFor, solveHomography, applyH, decodeImageData, StreamScanner };
})();
if (typeof module !== "undefined") module.exports = SVDec;
