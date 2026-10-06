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

/* Find anchor centroids in RGBA image data. Returns [tl,tr,bl,br] or null. */
function findAnchors(data, width, height){
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
  const out = [];
  for (let c = 0; c < 4; c++){
    if (cnt[c] < minArea) return null;
    out.push([sumX[c] / cnt[c], sumY[c] / cnt[c]]);
  }
  return out;
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

/* Full frame decode: RGBA data -> 2704-bit payload matrix, or null */
function decodeImageData(data, width, height){
  const anchors = findAnchors(data, width, height);
  if (!anchors) return null;
  // canonical anchor centers in cell units: (2,2) (62,2) (2,62) (62,62)
  const canonical = [[2,2],[62,2],[2,62],[62,62]];
  const H = solveHomography(canonical, anchors);
  if (!H) return null;

  const {INNER, OFFSET, FRAME_BITS} = S;
  // pass 1: center grays for adaptive threshold
  const centers = new Float32Array(FRAME_BITS);
  let lo = 255, hi = 0;
  for (let i = 0; i < FRAME_BITS; i++){
    const r = OFFSET + Math.floor(i / INNER), c = OFFSET + (i % INNER);
    const [X, Y] = applyH(H, c + 0.5, r + 0.5);
    const g = gray(data, width, X, Y);
    centers[i] = g; if (g < lo) lo = g; if (g > hi) hi = g;
  }
  const theta = (lo + hi) / 2;
  if (hi - lo < 40) return null;               // no contrast -> not a grid
  // pass 2: block-averaged sampling — 4x4 sub-samples within the central 50%
  // of each cell, then a global Otsu threshold on the 2,704 cell means.
  // (Matches the Python decoder's noise immunity: area averaging + Otsu,
  // not 5 point samples + midpoint threshold.)
  const SUB = [-0.225, -0.075, 0.075, 0.225];
  const means = new Float32Array(FRAME_BITS);
  for (let i = 0; i < FRAME_BITS; i++){
    const r = OFFSET + Math.floor(i / INNER), c = OFFSET + (i % INNER);
    let acc = 0;
    for (const dy of SUB) for (const dx of SUB){
      const [X, Y] = applyH(H, c + 0.5 + dx, r + 0.5 + dy);
      acc += gray(data, width, X, Y);
    }
    means[i] = acc / 16;
  }
  // Otsu is wrong here: picture-in-matrix art is MULTI-modal (soft inks and
  // tints sit between field and ink), and Otsu splits the biggest cluster.
  // The format contract pins the extremes instead: bit-1 ink is the darkest
  // tone, the payload field is the lightest — so threshold at their midpoint.
  let mLo = 255, mHi = 0;
  for (let i = 0; i < FRAME_BITS; i++){
    if (means[i] < mLo) mLo = means[i];
    if (means[i] > mHi) mHi = means[i];
  }
  const thetaB = (mLo + mHi) / 2;
  const bits = new Uint8Array(FRAME_BITS);
  for (let i = 0; i < FRAME_BITS; i++) bits[i] = means[i] < thetaB ? 1 : 0;
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
    const {seed, ctype, K, symbols} = S.unpackFrame(bits);
    this.framesSeen++; this.lastK = K;
    if (!this.lts.has(K)) this.lts.set(K, new S.LTDecoder(K));
    const lt = this.lts.get(K);
    for (let slot = 0; slot < 10; slot++){
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

return { classify, findAnchors, solveHomography, applyH, decodeImageData, StreamScanner };
})();
if (typeof module !== "undefined") module.exports = SVDec;
