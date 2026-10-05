/* spv.js — BMP-0003 (L3) SPV inclusion verifier, zero-dependency JS.
   Mirrors poc/svcode/spv.py exactly. Browser + Node (needs SVC + SVANCHOR). */
"use strict";
const SVSPV = (() => {
const _SVC = (typeof module !== "undefined") ? require("./svc.js") : SVC;
const _A = (typeof module !== "undefined") ? require("./anchor.js") : SVANCHOR;
const { hexToBytes, bytesToHex } = _SVC;
const sha256d = _A.sha256d;

const BEEF_V1 = [0x01, 0x00, 0xBE, 0xEF];
const FLAG_DUPLICATE = 0x01, FLAG_CLIENT_TXID = 0x02;

function rdVarint(b, off){
  const n = b[off]; off += 1;
  if (n < 0xFD) return [n, off];
  if (n === 0xFD) return [b[off] | (b[off+1] << 8), off + 2];
  if (n === 0xFE) return [(b[off] | b[off+1]<<8 | b[off+2]<<16 | b[off+3]<<24) >>> 0, off + 4];
  let v = 0n; for (let i = 0; i < 8; i++) v |= BigInt(b[off+i]) << (8n * BigInt(i));
  if (v > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error("varint too large");
  return [Number(v), off + 8];
}

/* ---------- BRC-74 BUMP ---------- */
function parseBumpFrom(b, off0){
  let off = off0;
  let blockHeight; [blockHeight, off] = rdVarint(b, off);
  const treeHeight = b[off]; off += 1;
  if (treeHeight === 0 || treeHeight > 64) throw new Error("bad tree height");
  const path = [];
  for (let level = 0; level < treeHeight; level++){
    let n; [n, off] = rdVarint(b, off);
    const leaves = [];
    for (let i = 0; i < n; i++){
      let offset; [offset, off] = rdVarint(b, off);
      const flags = b[off]; off += 1;
      let hash = null;
      if (!(flags & FLAG_DUPLICATE)){ hash = b.slice(off, off + 32); off += 32; }
      leaves.push({ offset, flags, hash });
    }
    leaves.sort((a, c) => a.offset - c.offset);
    path.push(leaves);
  }
  return [{ blockHeight, treeHeight, path }, off];
}

function parseBump(b){
  const [bump, off] = parseBumpFrom(b, 0);
  if (off !== b.length) throw new Error("trailing bytes after BUMP");
  return bump;
}

/* Merkle root (internal byte order, Uint8Array) for txid given as display hex. */
function bumpRoot(bump, txidDisplayHex){
  const txid = hexToBytes(txidDisplayHex).reverse();
  const leaf = bump.path[0].find(l => l.hash && eq(l.hash, txid));
  if (!leaf) throw new Error("txid not in BUMP level 0");
  const index = leaf.offset;
  let working = txid;
  for (let height = 0; height < bump.path.length; height++){
    const sibOff = (index >> height) ^ 1;
    const sib = bump.path[height].find(l => l.offset === sibOff);
    if (!sib) throw new Error(`missing sibling at level ${height}`);
    if (sib.flags & FLAG_DUPLICATE){
      working = sha256d(cat(working, working));
    } else if (sibOff & 1){
      working = sha256d(cat(working, sib.hash));   // working is LEFT child
    } else {
      working = sha256d(cat(sib.hash, working));   // working is RIGHT child
    }
  }
  return working;
}
function cat(a, b){ const o = new Uint8Array(a.length + b.length); o.set(a, 0); o.set(b, a.length); return o; }
function eq(a, b){ if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false; return true; }

/* ---------- BRC-62 BEEF v1 ---------- */
function parseRawTxStream(b, off){
  const start = off;
  off += 4;
  let nin; [nin, off] = rdVarint(b, off);
  for (let i = 0; i < nin; i++){
    off += 36;
    let slen; [slen, off] = rdVarint(b, off);
    off += slen + 4;
  }
  let nout; [nout, off] = rdVarint(b, off);
  for (let i = 0; i < nout; i++){
    off += 8;
    let slen; [slen, off] = rdVarint(b, off);
    off += slen;
  }
  off += 4;
  return [b.slice(start, off), off];
}

function parseBeef(b){
  if (!BEEF_V1.every((v, i) => b[i] === v)) throw new Error("not BEEF v1 (0100BEEF)");
  let off = 4;
  let nBumps; [nBumps, off] = rdVarint(b, off);
  const bumps = [];
  for (let i = 0; i < nBumps; i++){
    const [bump, noff] = parseBumpFrom(b, off);
    bumps.push(bump); off = noff;
  }
  let nTxs; [nTxs, off] = rdVarint(b, off);
  const txs = [];
  for (let i = 0; i < nTxs; i++){
    let raw; [raw, off] = parseRawTxStream(b, off);
    const hasBump = b[off]; off += 1;
    let bidx = null;
    if (hasBump){ [bidx, off] = rdVarint(b, off);
      if (bidx >= bumps.length) throw new Error("BUMP index out of range"); }
    txs.push({ raw, txid: bytesToHex(sha256d(raw).reverse()), bumpIndex: bidx });
  }
  if (off !== b.length) throw new Error("trailing bytes after BEEF");
  return { bumps, txs };
}

/* ---------- block headers ---------- */
function targetFromBits(bits){
  const exp = bits >>> 24, mant = BigInt(bits & 0x007FFFFF);
  if (bits & 0x00800000) throw new Error("negative target");
  return exp >= 3 ? mant << (8n * BigInt(exp - 3)) : mant >> (8n * BigInt(3 - exp));
}

function verifyHeader(header){
  if (header.length !== 80) throw new Error("header must be 80 bytes");
  const bits = (header[72] | header[73]<<8 | header[74]<<16 | header[75]<<24) >>> 0;
  const digest = sha256d(header);
  const hnum = bytesToBigLE(digest);
  if (hnum > targetFromBits(bits)) throw new Error("header fails proof-of-work");
  return { hash: bytesToHex(digest.slice().reverse()),
           merkleRoot: header.slice(36, 68),
           prevHash: header.slice(4, 36) };
}
function bytesToBigLE(b){ let v = 0n; for (let i = b.length - 1; i >= 0; i--) v = (v << 8n) | BigInt(b[i]); return v; }

/* ---------- BMP-0003 §3 pipeline ---------- */
/* headers: array of 80-byte Uint8Array. seen: optional Map for freshness.
   tipHeight: optional known tip for burial depth. Returns the envelope. */
function verifyL3(beef, authorityPubHex, headers, seen = null, tipHeight = null, minDepth = 1){
  const doc = parseBeef(beef);                                    // 1. parse
  const subject = doc.txs[doc.txs.length - 1];                    // 2. subject = last
  const byTxid = new Map(doc.txs.map(t => [t.txid, t]));

  const parsedSubject = _A.parseTx(subject.raw);
  const prevouts = [];                                            // 3. derive evidence
  for (const inp of parsedSubject.inputs){
    const ptxid = bytesToHex(inp.outpoint.slice(0, 32).slice().reverse());
    const pvout = inp.outpoint[32] | inp.outpoint[33]<<8 | inp.outpoint[34]<<16 | inp.outpoint[35]<<24;
    const anc = byTxid.get(ptxid);
    if (!anc) throw new Error(`ancestor ${ptxid.slice(0, 16)}… not in BEEF`);
    const ancParsed = _A.parseTx(anc.raw);
    if (pvout >= ancParsed.outputs.length)
      throw new Error("input references nonexistent ancestor output");
    const o = ancParsed.outputs[pvout];
    prevouts.push({ txid: ptxid, vout: pvout, value: Number(o.value),
                    script_hex: bytesToHex(o.script) });
  }
  const env = _A.verifyL2(subject.raw, prevouts, authorityPubHex, seen);  // 4. BMP-0002 §5

  const rootIndex = new Map();                                    // 5. inclusion
  for (const h of headers){
    const info = verifyHeader(h);                                 // PoW per header
    rootIndex.set(bytesToHex(info.merkleRoot), info);
  }
  for (const t of doc.txs){
    if (t.bumpIndex === null) continue;
    const bump = doc.bumps[t.bumpIndex];
    const root = bumpRoot(bump, t.txid);                          // 5a. BRC-74 walk
    if (!rootIndex.has(bytesToHex(root)))
      throw new Error(`tx ${t.txid.slice(0, 16)}…: merkle root not in header store`);
    if (tipHeight !== null){                                      // 5b. burial depth
      const depth = tipHeight - bump.blockHeight + 1;
      if (depth < minDepth) throw new Error(`insufficient burial depth ${depth} < ${minDepth}`);
    }
  }
  return env;
}

return { parseBump, bumpRoot, parseBeef, verifyHeader, verifyL3,
         targetFromBits, FLAG_DUPLICATE, FLAG_CLIENT_TXID };
})();
if (typeof module !== "undefined") module.exports = SVSPV;
