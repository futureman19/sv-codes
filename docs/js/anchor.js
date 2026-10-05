/* anchor.js — BMP-0002 (L2) on-chain anchoring verifier, zero-dependency JS.
   Mirrors poc/svcode/anchor.py exactly. Browser + Node (needs SVC loaded). */
"use strict";
const SVANCHOR = (() => {
const _SVC = (typeof module !== "undefined") ? require("./svc.js") : SVC;
const { sha256, ecdsaVerify, parsePubkey, hexToBytes, bytesToHex, bytesToBig, bigToBytes } = _SVC;
const sha256d = (b) => sha256(sha256(b));
const MAGIC = [0x42, 0x4D, 0x50, 0x31];           // "BMP1"
const SIGHASH_ALL_FORKID = 0x41;

/* ---------- bytes / varint helpers ---------- */
function concat(...arrs){
  const n = arrs.reduce((s, a) => s + a.length, 0);
  const out = new Uint8Array(n); let o = 0;
  for (const a of arrs){ out.set(a, o); o += a.length; }
  return out;
}
function rdVarint(b, off){
  const n = b[off]; off += 1;
  if (n < 0xFD) return [n, off];
  if (n === 0xFD) return [b[off] | (b[off+1] << 8), off + 2];
  if (n === 0xFE) return [(b[off] | b[off+1]<<8 | b[off+2]<<16 | b[off+3]<<24) >>> 0, off + 4];
  let v = 0n; for (let i = 0; i < 8; i++) v |= BigInt(b[off+i]) << (8n * BigInt(i));
  if (v > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error("varint too large");
  return [Number(v), off + 8];
}
function serVarint(n){
  if (n < 0xFD) return Uint8Array.of(n);
  if (n <= 0xFFFF) return Uint8Array.of(0xFD, n & 0xFF, n >> 8);
  if (n <= 0xFFFFFFFF) return Uint8Array.of(0xFE, n & 0xFF, (n>>8)&0xFF, (n>>16)&0xFF, (n>>>24)&0xFF);
  const b = new Uint8Array(9); b[0] = 0xFF;
  let v = BigInt(n); for (let i = 0; i < 8; i++){ b[1+i] = Number(v & 0xFFn); v >>= 8n; }
  return b;
}
const le = (n, len) => bigToBytes(BigInt(n), len).reverse();  // bigToBytes is BE; reverse → LE
function eqBytes(a, b){ if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false; return true; }

/* ---------- transaction parsing ---------- */
function parseTx(raw){
  let off = 0;
  const version = raw[0] | raw[1]<<8 | raw[2]<<16 | raw[3]<<24; off = 4;
  let nin; [nin, off] = rdVarint(raw, off);
  const inputs = [];
  for (let i = 0; i < nin; i++){
    const outpoint = raw.slice(off, off + 36); off += 36;
    let slen; [slen, off] = rdVarint(raw, off);
    const scriptSig = raw.slice(off, off + slen); off += slen;
    const sequence = raw.slice(off, off + 4); off += 4;
    inputs.push({ outpoint, scriptSig, sequence });
  }
  let nout; [nout, off] = rdVarint(raw, off);
  const outputs = [];
  for (let i = 0; i < nout; i++){
    const value = bytesToBig(raw.slice(off, off + 8).slice().reverse()); off += 8; // LE → BigInt
    let slen; [slen, off] = rdVarint(raw, off);
    const script = raw.slice(off, off + slen); off += slen;
    outputs.push({ value, script });
  }
  const locktime = (raw[off] | raw[off+1]<<8 | raw[off+2]<<16 | raw[off+3]<<24) >>> 0; off += 4;
  if (off !== raw.length) throw new Error("trailing bytes after locktime");
  const txid = bytesToHex(sha256d(raw).reverse());
  return { version, inputs, outputs, locktime, txid };
}

function readPush(script, off){
  const op = script[off]; off += 1;
  let ln;
  if (op <= 75) ln = op;
  else if (op === 0x4C){ ln = script[off]; off += 1; }
  else if (op === 0x4D){ ln = script[off] | (script[off+1] << 8); off += 2; }
  else if (op === 0x4E){ ln = (script[off] | script[off+1]<<8 | script[off+2]<<16 | script[off+3]<<24) >>> 0; off += 4; }
  else throw new Error(`opcode 0x${op.toString(16)} is not a push`);
  const data = script.slice(off, off + ln);
  if (data.length !== ln) throw new Error("truncated push");
  return [data, off + ln];
}

function parseP2pkhScriptSig(ss){
  const [sigPlus, off1] = readPush(ss, 0);
  const [pub, off2] = readPush(ss, off1);
  if (off2 !== ss.length) throw new Error("extra data in scriptSig");
  const sighashByte = sigPlus[sigPlus.length - 1];
  return { sigCompact: derToCompact(sigPlus.slice(0, -1)), sighashByte, pub };
}

function derToCompact(der){
  // 30 <len> 02 <rlen> <r> 02 <slen> <s>
  if (der[0] !== 0x30) throw new Error("bad DER sig");
  const rlen = der[3];
  let r = bytesToBig(der.slice(4, 4 + rlen));
  const sOff = 4 + rlen;
  if (der[sOff] !== 0x02) throw new Error("bad DER sig");
  const slen = der[sOff + 1];
  let s = bytesToBig(der.slice(sOff + 2, sOff + 2 + slen));
  if (s > _SVC.Nn / 2n) s = _SVC.Nn - s;   // normalize to low-s for ecdsaVerify
  return concat(bigToBytes(r, 32), bigToBytes(s, 32));
}

const isP2pkh = (s) => s.length === 25 && s[0] === 0x76 && s[1] === 0xA9 &&
                       s[2] === 0x14 && s[23] === 0x88 && s[24] === 0xAC;

/* ---------- sighash ---------- */
const serOutput = (o) => concat(le(o.value, 8), serVarint(o.script.length), o.script);

function sighashForkid(inputs, outputs, idx, scriptCode, value, sighashType = SIGHASH_ALL_FORKID, version = 1, locktime = 0){
  const hp = sha256d(concat(...inputs.map(i => i.outpoint)));
  const hs = sha256d(concat(...inputs.map(i => i.sequence)));
  const ho = sha256d(concat(...outputs.map(serOutput)));
  const inp = inputs[idx];
  const pre = concat(
    le(version, 4), hp, hs,
    inp.outpoint, serVarint(scriptCode.length), scriptCode,
    le(value, 8), inp.sequence,
    ho, le(locktime, 4), le(sighashType, 4));
  return sha256d(pre);
}

/* ---------- BMP-0002 §5 validation ---------- */
function extractEnvelope(raw){
  const parsed = parseTx(raw);
  let found = null;
  for (const o of parsed.outputs){
    const s = o.script;
    if (s.length >= 2 && s[0] === 0x00 && s[1] === 0x6A){
      let push, off;
      try { [push, off] = readPush(s, 2); } catch { continue; }
      if (off === s.length && push.length >= 4 && MAGIC.every((m, i) => push[i] === m)){
        if (found !== null) throw new Error("multiple BMP1 data outputs");
        found = push.slice(4);
      }
    }
  }
  if (found === null) throw new Error("no BMP1 data output");
  return found;
}

/* prevouts: [{txid(display hex), vout, value(sats), script_hex}]
   seen: optional Map outpointHex -> txid for the freshness rule.
   Returns the parsed envelope (SVC.parseEnvelope shape). Throws on failure. */
function verifyL2(raw, prevouts, authorityPubHex, seen = null){
  const parsed = parseTx(raw);                                    // 1. parse
  const envBytes = extractEnvelope(raw);
  const env = _SVC.parseEnvelope(envBytes);                       // 2. envelope
  if (!_SVC.ecdsaVerify(_SVC.parsePubkey(authorityPubHex),        // 3. authority
                        env.signature, _SVC.envelopeDigest(envBytes)))
    throw new Error("envelope signature invalid");

  const evidence = new Map(prevouts.map(p => [p.txid + ":" + p.vout, p]));
  let totalIn = 0n;
  for (let i = 0; i < parsed.inputs.length; i++){                 // 4. payment evidence
    const inp = parsed.inputs[i];
    const txid = bytesToHex(inp.outpoint.slice(0, 32).slice().reverse());
    const vout = inp.outpoint[32] | inp.outpoint[33]<<8 | inp.outpoint[34]<<16 | inp.outpoint[35]<<24;
    const ev = evidence.get(txid + ":" + vout);
    if (!ev) throw new Error(`missing prevout evidence for input ${i}`);
    const prevScript = hexToBytes(ev.script_hex);
    if (!isP2pkh(prevScript)) throw new Error(`prevout ${i} is not P2PKH`);
    const { sigCompact, sighashByte, pub } = parseP2pkhScriptSig(inp.scriptSig);
    if (sighashByte !== SIGHASH_ALL_FORKID) throw new Error(`input ${i} wrong sighash type`);
    // hash160(pub) == prevScript[3:23]
    const h160 = _SVC.sha256(pub);                                 // sha then ripemd:
    const ripe = ripemd160(h160);
    if (!eqBytes(ripe, prevScript.slice(3, 23)))
      throw new Error(`input ${i} pubkey does not match prevout`);
    const structured = parsed.inputs.map(x => ({ outpoint: x.outpoint, sequence: x.sequence }));
    const digest = sighashForkid(structured, parsed.outputs, i, prevScript, ev.value,
                                 SIGHASH_ALL_FORKID, parsed.version, parsed.locktime);
    if (!ecdsaVerify(parsePubkey(bytesToHex(pub)), sigCompact, digest))
      throw new Error(`input ${i} signature invalid`);
    totalIn += BigInt(ev.value);
  }
  const totalOut = parsed.outputs.reduce((s, o) => s + o.value, 0n);
  if (totalIn - totalOut <= 0n) throw new Error("no fee paid");   // 5. fee

  if (seen){                                                      // 6. freshness
    for (const inp of parsed.inputs){
      const key = bytesToHex(inp.outpoint);
      const prior = seen.get(key);
      if (prior && prior !== parsed.txid)
        throw new Error("double-spend: outpoint already backs another command");
    }
    for (const inp of parsed.inputs) seen.set(bytesToHex(inp.outpoint), parsed.txid);
  }
  return env;
}

/* RIPEMD-160 (zero-dep; only used for pubkey-hash check).
   Transplanted verbatim from docs/js/miniwallet.js (proven against the
   canonical privkey=1 address vector in mwtest). */
const RL = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,7,4,13,1,10,6,15,3,12,0,9,5,2,14,11,8,3,10,14,4,9,15,8,1,2,7,0,6,13,11,5,12,1,9,11,10,0,8,12,4,13,3,7,15,14,5,6,2,4,0,5,9,7,12,2,10,14,1,3,8,11,6,15,13];
const RR = [5,14,7,0,9,2,11,4,13,6,15,8,1,10,3,12,6,11,3,7,0,13,5,10,14,15,8,12,4,9,1,2,15,5,1,3,7,14,6,9,11,8,12,2,10,0,4,13,8,6,4,1,3,11,15,0,5,12,2,13,9,7,10,14,12,15,10,4,1,5,8,7,6,2,13,14,0,3,9,11];
const SL = [11,14,15,12,5,8,7,9,11,13,14,15,6,7,9,8,7,6,8,13,11,9,7,15,7,12,15,9,11,7,13,12,11,13,6,7,14,9,13,15,14,8,13,6,5,12,7,5,11,12,14,15,14,15,9,8,9,14,5,6,8,6,5,12,9,15,5,11,6,8,13,12,5,12,13,14,11,8,5,6];
const SR = [8,9,9,11,13,15,15,5,7,7,8,11,14,14,12,6,9,13,15,7,12,8,9,11,7,7,12,7,6,15,13,11,9,7,15,11,8,6,6,14,12,13,5,14,13,13,7,5,15,5,8,11,14,14,6,14,6,9,12,9,12,5,15,8,8,5,12,9,12,5,14,6,8,13,6,5,15,13,11,11];
const KL = [0x00000000,0x5A827999,0x6ED9EBA1,0x8F1BBCDC,0xA953FD4E];
const KR = [0x50A28BE6,0x5C4DD124,0x6D703EF3,0x7A6D76E9,0x00000000];

function _rol(x, n){ return ((x << n) | (x >>> (32 - n))) >>> 0; }
function _rf(j, x, y, z){
  if (j < 16) return (x ^ y ^ z) >>> 0;
  if (j < 32) return ((x & y) | (~x & z)) >>> 0;
  if (j < 48) return ((x | ~y) ^ z) >>> 0;
  if (j < 64) return ((x & z) | (y & ~z)) >>> 0;
  return (x ^ (y | ~z)) >>> 0;
}

function ripemd160(msg){
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
      let t = (_rol((a + _rf(j, b, c, d) + X[RL[j]] + KL[bl]) >>> 0, SL[j]) + e) >>> 0;
      a = e; e = d; d = _rol(c, 10); c = b; b = t;
      t = (_rol((aa + _rf(79 - j, bb, cc, dd) + X[RR[j]] + KR[bl]) >>> 0, SR[j]) + ee) >>> 0;
      aa = ee; ee = dd; dd = _rol(cc, 10); cc = bb; bb = t;
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

return { parseTx, readPush, extractEnvelope, sighashForkid, verifyL2,
         serVarint, sha256d, derToCompact, ripemd160, SIGHASH_ALL_FORKID };
})();
if (typeof module !== "undefined") module.exports = SVANCHOR;
