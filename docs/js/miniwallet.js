/* miniwallet.js — BSV address + WIF from a raw private key.
   Zero dependencies beyond SVC (sha256 + secp256k1). Browser + Node. */
"use strict";
const MiniWallet = (() => {
const S = SVC;

/* ---------- RIPEMD-160 (pure JS) ---------- */
const RL = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,7,4,13,1,10,6,15,3,12,0,9,5,2,14,11,8,3,10,14,4,9,15,8,1,2,7,0,6,13,11,5,12,1,9,11,10,0,8,12,4,13,3,7,15,14,5,6,2,4,0,5,9,7,12,2,10,14,1,3,8,11,6,15,13];
const RR = [5,14,7,0,9,2,11,4,13,6,15,8,1,10,3,12,6,11,3,7,0,13,5,10,14,15,8,12,4,9,1,2,15,5,1,3,7,14,6,9,11,8,12,2,10,0,4,13,8,6,4,1,3,11,15,0,5,12,2,13,9,7,10,14,12,15,10,4,1,5,8,7,6,2,13,14,0,3,9,11];
const SL = [11,14,15,12,5,8,7,9,11,13,14,15,6,7,9,8,7,6,8,13,11,9,7,15,7,12,15,9,11,7,13,12,11,13,6,7,14,9,13,15,14,8,13,6,5,12,7,5,11,12,14,15,14,15,9,8,9,14,5,6,8,6,5,12,9,15,5,11,6,8,13,12,5,12,13,14,11,8,5,6];
const SR = [8,9,9,11,13,15,15,5,7,7,8,11,14,14,12,6,9,13,15,7,12,8,9,11,7,7,12,7,6,15,13,11,9,7,15,11,8,6,6,14,12,13,5,14,13,13,7,5,15,5,8,11,14,14,6,14,6,9,12,9,12,5,15,8,8,5,12,9,12,5,14,6,8,13,6,5,15,13,11,11];
const KL = [0x00000000,0x5A827999,0x6ED9EBA1,0x8F1BBCDC,0xA953FD4E];
const KR = [0x50A28BE6,0x5C4DD124,0x6D703EF3,0x7A6D76E9,0x00000000];

function rol(x, n){ return ((x << n) | (x >>> (32 - n))) >>> 0; }
function f(j, x, y, z){
  if (j < 16) return (x ^ y ^ z) >>> 0;
  if (j < 32) return ((x & y) | (~x & z)) >>> 0;
  if (j < 48) return ((x | ~y) ^ z) >>> 0;
  if (j < 64) return ((x & z) | (y & ~z)) >>> 0;
  return (x ^ (y | ~z)) >>> 0;
}

function ripemd160(msg){
  // pad: 0x80, zeros, 8-byte LE bit length
  const bitLen = msg.length * 8;
  let len = msg.length + 1;
  while (len % 64 !== 56) len++;
  const buf = new Uint8Array(len + 8);
  buf.set(msg); buf[msg.length] = 0x80;
  for (let i = 0; i < 8; i++) buf[len + i] = (bitLen / Math.pow(2, 8 * i)) & 0xff;
  let h0 = 0x67452301, h1 = 0xEFCDAB89, h2 = 0x98BADCFE, h3 = 0x10325476, h4 = 0xC3D2E1F0;
  for (let off = 0; off < buf.length; off += 64){
    const X = new Array(16);
    for (let i = 0; i < 16; i++)
      X[i] = (buf[off+4*i] | (buf[off+4*i+1] << 8) | (buf[off+4*i+2] << 16) | (buf[off+4*i+3] << 24)) >>> 0;
    let a = h0, b = h1, c = h2, d = h3, e = h4;
    let aa = h0, bb = h1, cc = h2, dd = h3, ee = h4;
    for (let j = 0; j < 80; j++){
      const bl = j >> 4;
      let t = (rol((a + f(j, b, c, d) + X[RL[j]] + KL[bl]) >>> 0, SL[j]) + e) >>> 0;
      a = e; e = d; d = rol(c, 10); c = b; b = t;
      t = (rol((aa + f(79 - j, bb, cc, dd) + X[RR[j]] + KR[bl]) >>> 0, SR[j]) + ee) >>> 0;
      aa = ee; ee = dd; dd = rol(cc, 10); cc = bb; bb = t;
    }
    const t = (h1 + c + dd) >>> 0;
    h1 = (h2 + d + ee) >>> 0;
    h2 = (h3 + e + aa) >>> 0;
    h3 = (h4 + a + bb) >>> 0;
    h4 = (h0 + b + cc) >>> 0;
    h0 = t;
  }
  const out = new Uint8Array(20);
  const hs = [h0, h1, h2, h3, h4];
  for (let i = 0; i < 5; i++)
    for (let j = 0; j < 4; j++) out[4*i+j] = (hs[i] >>> (8*j)) & 0xff;
  return out;
}

function hash160(b){ return ripemd160(S.sha256(b)); }

/* ---------- Base58Check ---------- */
const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function base58Encode(bytes){
  let zeros = 0;
  while (zeros < bytes.length && bytes[zeros] === 0) zeros++;
  let n = 0n;
  for (const b of bytes) n = n * 256n + BigInt(b);
  let s = "";
  while (n > 0n){ s = B58[Number(n % 58n)] + s; n /= 58n; }
  return "1".repeat(zeros) + s;
}
function b58check(version, payload){
  const b = new Uint8Array(1 + payload.length);
  b[0] = version; b.set(payload, 1);
  const chk = S.sha256(S.sha256(b)).slice(0, 4);
  const full = new Uint8Array(b.length + 4);
  full.set(b); full.set(chk, b.length);
  return base58Encode(full);
}

/* ---------- Wallet ---------- */
function fromPriv(privBytes){
  // returns {wif, address, pubHex}
  const Q = S.pubkeyFromPriv(S.bytesToBig(privBytes));
  const pubHex = S.compressPubkey(Q);          // svc.js returns a hex string
  const pub = S.hexToBytes(pubHex);
  const address = b58check(0x00, hash160(pub));
  const ext = new Uint8Array(33); ext.set(privBytes); ext[32] = 0x01; // compressed flag
  const wif = b58check(0x80, ext);
  return { wif, address, pubHex };
}
function randomPriv(){
  const b = new Uint8Array(32);
  for (;;){
    (typeof crypto !== "undefined" ? crypto : require("crypto").webcrypto).getRandomValues(b);
    const n = S.bytesToBig(b);
    if (n > 0n && n < S.Nn) return b;
  }
}
return { ripemd160, hash160, base58Encode, b58check, fromPriv, randomPriv };
})();
if (typeof module !== "undefined") module.exports = MiniWallet;
