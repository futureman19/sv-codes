/* svc.js — SV Code shared core: crypto, envelope, stream, fountain, frame.
   Zero dependencies. Bit-exact with the Python reference (poc/svcode/).
   Spec: SV-0001 (visual matrix) + BMP-0000 (envelope), repo root /spec. */
"use strict";
const SVC = (() => {

/* ---------- SHA-256 (sync) ---------- */
const K256 = new Uint32Array([
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]);
const rotr = (x,n)=>((x>>>n)|(x<<(32-n)))>>>0;
function sha256(bytes){
  const l=bytes.length, bitLen=l*8;
  const pl=(((l+8)>>6)+1)<<6;
  const m=new Uint8Array(pl); m.set(bytes); m[l]=0x80;
  const dv=new DataView(m.buffer);
  dv.setUint32(pl-8, Math.floor(bitLen/4294967296)); dv.setUint32(pl-4, bitLen>>>0);
  let h0=0x6a09e667,h1=0xbb67ae85,h2=0x3c6ef372,h3=0xa54ff53a,
      h4=0x510e527f,h5=0x9b05688c,h6=0x1f83d9ab,h7=0x5be0cd19;
  const w=new Uint32Array(64);
  for(let off=0;off<pl;off+=64){
    for(let t=0;t<16;t++) w[t]=dv.getUint32(off+t*4);
    for(let t=16;t<64;t++){
      const s0=(rotr(w[t-15],7)^rotr(w[t-15],18)^(w[t-15]>>>3))>>>0;
      const s1=(rotr(w[t-2],17)^rotr(w[t-2],19)^(w[t-2]>>>10))>>>0;
      w[t]=(w[t-16]+s0+w[t-7]+s1)>>>0;
    }
    let a=h0,b=h1,c=h2,d=h3,e=h4,f=h5,g=h6,h=h7;
    for(let t=0;t<64;t++){
      const S1=(rotr(e,6)^rotr(e,11)^rotr(e,25))>>>0;
      const ch=((e&f)^((~e)&g))>>>0;
      const t1=(h+S1+ch+K256[t]+w[t])>>>0;
      const S0=(rotr(a,2)^rotr(a,13)^rotr(a,22))>>>0;
      const mj=((a&b)^(a&c)^(b&c))>>>0;
      const t2=(S0+mj)>>>0;
      h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
    }
    h0=(h0+a)>>>0;h1=(h1+b)>>>0;h2=(h2+c)>>>0;h3=(h3+d)>>>0;
    h4=(h4+e)>>>0;h5=(h5+f)>>>0;h6=(h6+g)>>>0;h7=(h7+h)>>>0;
  }
  const out=new Uint8Array(32), ov=new DataView(out.buffer);
  [h0,h1,h2,h3,h4,h5,h6,h7].forEach((h,i)=>ov.setUint32(i*4,h));
  return out;
}
function hmacSha256(key, msg){
  const k = key.length>64 ? sha256(key) : key;
  const kb = new Uint8Array(64); kb.set(k);
  const ipad = new Uint8Array(64), opad = new Uint8Array(64);
  for(let i=0;i<64;i++){ ipad[i]=kb[i]^0x36; opad[i]=kb[i]^0x5c; }
  const inner = new Uint8Array(64+msg.length); inner.set(ipad); inner.set(msg,64);
  const ih = sha256(inner);
  const outer = new Uint8Array(96); outer.set(opad); outer.set(ih,64);
  return sha256(outer);
}

/* ---------- CRC-32 (IEEE) ---------- */
const CRC_T=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;
  for(let k=0;k<8;k++)c=(c&1)?(0xEDB88320^(c>>>1)):(c>>>1);t[n]=c>>>0}return t})();
function crc32(bytes){let c=0xFFFFFFFF;
  for(let i=0;i<bytes.length;i++)c=CRC_T[(c^bytes[i])&0xFF]^(c>>>8);
  return (c^0xFFFFFFFF)>>>0}

/* ---------- secp256k1 (BigInt, affine) ---------- */
const P  = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2Fn;
const Nn = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141n;
const GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798n;
const GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8n;
const G = {x:GX, y:GY};
const mod = (a,m)=>{const r=a%m; return r<0n?r+m:r};
/* Extended Euclidean inverse */
function invMod(a, m){
  a = mod(a, m);
  let [old_r, r] = [a, m];
  let [old_s, s] = [1n, 0n];
  while (r !== 0n){
    const q = old_r / r;
    [old_r, r] = [r, old_r - q*r];
    [old_s, s] = [s, old_s - q*s];
  }
  return mod(old_s, m);
}
function ptAdd(A, B){
  if (A === null) return B;
  if (B === null) return A;
  if (A.x === B.x){
    if (mod(A.y + B.y, P) === 0n) return null;         // A + (-A) = O
    const s = mod((3n*A.x*A.x) * invMod(2n*A.y, P), P); // doubling
    const x = mod(s*s - 2n*A.x, P);
    return {x, y: mod(s*(A.x - x) - A.y, P)};
  }
  const s = mod((B.y - A.y) * invMod(B.x - A.x, P), P);
  const x = mod(s*s - A.x - B.x, P);
  return {x, y: mod(s*(A.x - x) - A.y, P)};
}
function ptMul(k, A){
  let R = null, B = A;
  while (k > 0n){
    if (k & 1n) R = ptAdd(R, B);
    B = ptAdd(B, B);
    k >>= 1n;
  }
  return R;
}
function pubkeyFromPriv(priv){ return ptMul(mod(priv, Nn), G); }
function liftX(x, odd){
  const y2 = mod(x*x*x + 7n, P);
  let y = modPow(y2, (P+1n)/4n, P);
  if ((y & 1n) !== (odd ? 1n : 0n)) y = P - y;
  return {x, y};
}
function modPow(b, e, m){
  let r = 1n; b = mod(b, m);
  while (e > 0n){ if (e & 1n) r = mod(r*b, m); b = mod(b*b, m); e >>= 1n; }
  return r;
}
function parsePubkey(hex){
  const b = hexToBytes(hex);
  if (b.length === 33 && (b[0] === 2 || b[0] === 3)){
    const x = bytesToBig(b.subarray(1));
    return liftX(x, b[0] === 3);
  }
  if (b.length === 64) return {x: bytesToBig(b.subarray(0,32)), y: bytesToBig(b.subarray(32))};
  throw new Error("bad pubkey");
}
function compressPubkey(Q){
  const out = new Uint8Array(33);
  out[0] = (Q.y & 1n) ? 3 : 2;
  out.set(bigToBytes(Q.x, 32), 1);
  return bytesToHex(out);
}
/* ECDSA verify: sig = r||s (64B), digest = 32B. Enforces low-s. */
function ecdsaVerify(Q, sig, digest){
  if (sig.length !== 64) return false;
  const r = bytesToBig(sig.subarray(0,32));
  let s = bytesToBig(sig.subarray(32));
  if (r < 1n || r >= Nn || s < 1n || s >= Nn) return false;
  if (s > Nn/2n) return false;                       // low-s rule (BMP-0000 §4.3)
  const z = bytesToBig(digest);
  const w = invMod(s, Nn);
  const P1 = ptMul(mod(z*w, Nn), G);
  const P2 = ptMul(mod(r*w, Nn), Q);
  const R = ptAdd(P1, P2);
  if (R === null) return false;
  return mod(R.x, Nn) === r;
}
/* RFC 6979 deterministic k (HMAC-SHA256) + ECDSA sign, low-s normalized */
function rfc6979K(priv, digest){
  const x = bigToBytes(priv, 32);
  const h1 = digest;
  let V = new Uint8Array(32).fill(1), K = new Uint8Array(32).fill(0);
  const seed1 = new Uint8Array(97); seed1.set(V); seed1[32]=0; seed1.set(x,33); seed1.set(h1,65);
  K = hmacSha256(K, seed1); V = hmacSha256(K, V);
  const seed2 = new Uint8Array(97); seed2.set(V); seed2[32]=1; seed2.set(x,33); seed2.set(h1,65);
  K = hmacSha256(K, seed2); V = hmacSha256(K, V);
  for(;;){
    V = hmacSha256(K, V);
    const k = bytesToBig(V);
    if (k >= 1n && k < Nn) return k;
    K = hmacSha256(K, (()=>{const t=new Uint8Array(33);t.set(V);t[32]=0;return t})());
    V = hmacSha256(K, V);
  }
}
function ecdsaSign(priv, digest){
  const z = bytesToBig(digest);
  for(;;){
    const k = rfc6979K(priv, digest);
    const R = ptMul(k, G);
    const r = mod(R.x, Nn);
    if (r === 0n) continue;
    let s = mod(invMod(k, Nn) * (z + r*priv), Nn);
    if (s === 0n) continue;
    if (s > Nn/2n) s = Nn - s;                       // low-s
    const sig = new Uint8Array(64);
    sig.set(bigToBytes(r,32), 0); sig.set(bigToBytes(s,32), 32);
    return sig;
  }
}

/* ---------- byte utils ---------- */
function hexToBytes(h){ const b=new Uint8Array(h.length/2);
  for(let i=0;i<b.length;i++) b[i]=parseInt(h.substr(i*2,2),16); return b; }
function bytesToHex(b){ return Array.from(b).map(x=>x.toString(16).padStart(2,"0")).join(""); }
function bytesToBig(b){ let v=0n; for(const x of b) v=(v<<8n)|BigInt(x); return v; }
function bigToBytes(v, len){ const b=new Uint8Array(len);
  for(let i=len-1;i>=0;i--){ b[i]=Number(v & 0xFFn); v >>= 8n; } return b; }

/* ---------- BMP envelope (BMP-0000 §4) ---------- */
function buildEnvelopeFields(targetId, action, params8, nonce, payload, sig64){
  const env = new Uint8Array(85 + payload.length);
  const dv = new DataView(env.buffer);
  dv.setUint8(0, 0x01);
  dv.setUint32(1, targetId >>> 0);
  dv.setUint16(5, action);
  env.set(params8, 7);
  dv.setUint32(15, nonce >>> 0);
  dv.setUint16(19, payload.length);
  env.set(sig64, 21);
  env.set(payload, 85);
  return env;
}
function envelopeDigest(env){
  // SHA-256 over header (0..20) + payload (85..)
  const h = new Uint8Array(21 + (env.length - 85));
  h.set(env.subarray(0,21)); h.set(env.subarray(85), 21);
  return sha256(h);
}
function parseEnvelope(data){
  if (data.length < 85) throw new Error("envelope too short");
  const dv = new DataView(data.buffer, data.byteOffset, data.length);
  if (data[0] !== 1) throw new Error("bad version");
  const plen = dv.getUint16(19);
  if (data.length !== 85 + plen) throw new Error("length mismatch");
  return {
    version: 1,
    targetId: dv.getUint32(1),
    action: dv.getUint16(5),
    params: data.slice(7,15),
    nonce: dv.getUint32(15),
    signature: data.slice(21,85),
    payload: data.slice(85),
  };
}

/* ---------- stream framing (SV-0001 §3.1) ---------- */
function buildStream(content){
  const raw = 8 + content.length;
  const padded = Math.ceil(raw/32)*32;
  const s = new Uint8Array(padded);
  const dv = new DataView(s.buffer);
  dv.setUint32(0, content.length);
  dv.setUint32(4, crc32(content));
  s.set(content, 8);
  return s;
}
function parseStream(buf){
  if (buf.length < 8 || buf.length % 32) throw new Error("malformed stream");
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.length);
  const clen = dv.getUint32(0), crc = dv.getUint32(4);
  if (8 + clen > buf.length) throw new Error("length overrun");
  const content = buf.slice(8, 8+clen);
  if (crc32(content) !== crc) throw new Error("CRC32 mismatch");
  return content;
}

/* ---------- fountain (SV-0001 §3.2) ---------- */
function randStream(seed, slot){
  const base = new Uint8Array([0x53,0x56,0x31,(seed>>8)&0xFF,seed&0xFF,slot&0xFF]);
  let block = 0, buf = new Uint8Array(0), pos = 0;
  return { u32(){
    if (pos + 4 > buf.length){
      const ib = new Uint8Array(base.length+4); ib.set(base);
      new DataView(ib.buffer).setUint32(base.length, block++);
      const nb = sha256(ib);
      const cat = new Uint8Array(buf.length - pos + 32);
      cat.set(buf.subarray(pos)); cat.set(nb, buf.length-pos);
      buf = cat; pos = 0;
    }
    const v = ((buf[pos]<<24)|(buf[pos+1]<<16)|(buf[pos+2]<<8)|buf[pos+3])>>>0;
    pos += 4; return v;
  }};
}
function solitonCDF(K){
  const c=0.1, delta=0.5, R=c*Math.log(K/delta)*Math.sqrt(K);
  const tau=new Array(K+1).fill(0);
  const cut=Math.max(1, Math.floor(K/R));
  for(let d=1; d<cut; d++) tau[d]=R/(d*K);
  if (cut<=K) tau[cut]+=R*Math.log(R/delta)/K;
  const rho=d=>d===1?1/K:1/(d*(d-1));
  let Z=0; const mu=new Array(K+1).fill(0);
  for(let d=1; d<=K; d++){ mu[d]=rho(d)+tau[d]; Z+=mu[d]; }
  const cdf=new Array(K+1).fill(0); let acc=0;
  for(let d=1; d<=K; d++){ acc+=mu[d]/Z; cdf[d]=acc; }
  return cdf;
}
function sampleDegree(cdf, u){
  for(let d=1; d<cdf.length; d++) if (u<=cdf[d]) return d;
  return cdf.length-1;
}
function pickIndices(K, cdf, seed, slot){
  const rng = randStream(seed, slot);
  const d = Math.min(sampleDegree(cdf, rng.u32()/4294967296), K);
  const picked = new Set();
  while (picked.size < d) picked.add(rng.u32() % K);
  return picked;
}
function encodeSymbol(symbols, cdf, seed, slot){
  const K = symbols.length;
  if (seed === 0) return slot < K ? symbols[slot] : new Uint8Array(32);
  const sym = new Uint8Array(32);
  for (const idx of pickIndices(K, cdf, seed, slot)){
    const src = symbols[idx];
    for (let b=0;b<32;b++) sym[b] ^= src[b];
  }
  return sym;
}
/* symmetric difference of two Sets */
function symdiff(a, b){
  const out = new Set();
  for (const x of a) if (!b.has(x)) out.add(x);
  for (const x of b) if (!a.has(x)) out.add(x);
  return out;
}
/* Incremental LT decoder over GF(2) */
class LTDecoder {
  constructor(K){ this.K=K; this.cdf=solitonCDF(K); this.rows=[]; this.seen=new Set(); }
  add(seed, slot, data){
    const key = seed+":"+slot;
    if (this.seen.has(key)) return this.solved() !== null;
    this.seen.add(key);
    let coeffs;
    if (seed === 0){ if (slot >= this.K) return false; coeffs = new Set([slot]); }
    else coeffs = pickIndices(this.K, this.cdf, seed, slot);
    let row = new Uint8Array(data);
    // reduce against existing pivot rows: row := row XOR pivotRow
    for (const r of this.rows){
      if (coeffs.has(r.pivot)){
        coeffs = symdiff(coeffs, r.coeffs);
        for (let b=0;b<32;b++) row[b] ^= r.data[b];
      }
    }
    if (coeffs.size === 0) return this.solved() !== null;
    const pivot = Math.min(...coeffs);
    // eliminate this pivot from existing rows: pivotRow := pivotRow XOR row
    for (const r of this.rows){
      if (r.coeffs.has(pivot)){
        r.coeffs = symdiff(r.coeffs, coeffs);
        for (let b=0;b<32;b++) r.data[b] ^= row[b];
      }
    }
    this.rows.push({coeffs, data: row, pivot});
    return this.rows.length === this.K;
  }
  count(){ return this.rows.length; }
  solved(){
    if (this.rows.length !== this.K) return null;
    const out = new Array(this.K).fill(null);
    for (const r of this.rows){
      if (r.coeffs.size !== 1 || !r.coeffs.has(r.pivot)) return null;
      out[r.pivot] = r.data;
    }
    return out.some(s=>s===null) ? null : out;
  }
}

/* ---------- frame (SV-0001 §3) ---------- */
const FRAME_BITS = 2704, GRID = 64, INNER = 52, OFFSET = 6;
function packFrame(symbols10, seed, ctype, K){
  const bits = new Uint8Array(FRAME_BITS);
  let n = 0;
  const put = (v, c) => { for(let b=c-1;b>=0;b--) bits[n++] = (v>>>b)&1; };
  const putBytes = (bs) => { for(const x of bs) put(x, 8); };
  put(seed, 16); put(ctype, 8); put(K, 16);
  for (const s of symbols10) putBytes(s);
  return bits;
}
function unpackFrame(bits){
  const read = (off, n) => { let v=0; for(let i=0;i<n;i++) v=(v<<1)|bits[off+i]; return v>>>0; };
  const seed = read(0,16), ctype = read(16,8), K = read(24,16);
  const symbols = [];
  for (let slot=0; slot<10; slot++){
    const base = 40 + slot*256, sym = new Uint8Array(32);
    for (let b=0;b<32;b++) sym[b] = read(base + b*8, 8);
    symbols.push(sym);
  }
  return {seed, ctype, K, symbols};
}

return { sha256, hmacSha256, crc32,
  P, Nn, G, ptAdd, ptMul, invMod, pubkeyFromPriv, parsePubkey, compressPubkey,
  ecdsaVerify, ecdsaSign, rfc6979K,
  hexToBytes, bytesToHex, bytesToBig, bigToBytes,
  buildEnvelopeFields, envelopeDigest, parseEnvelope,
  buildStream, parseStream,
  randStream, solitonCDF, sampleDegree, pickIndices, encodeSymbol, LTDecoder,
  FRAME_BITS, GRID, INNER, OFFSET, packFrame, unpackFrame };
})();
if (typeof module !== "undefined") module.exports = SVC;
