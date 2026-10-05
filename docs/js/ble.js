/* ble.js — BMP-0001 (BMP-BLE) fragmentation/reassembly in zero-dependency JS.
   Mirrors poc/svcode/ble.py exactly. Browser + Node. */
"use strict";
const SVBLE = (() => {
const COMPANY = 0xFFFF;
const MAGIC0 = 0x53, MAGIC1 = 0x56;           // "SV"
const LEGACY_MTU = 19, EXTENDED_MTU = 251, HEADER = 5;

function fragment(stream, seq = 0, mtu = LEGACY_MTU){
  if (!stream.length) throw new Error("empty stream");
  const count = Math.ceil(stream.length / mtu);
  if (count > 255) throw new Error("stream too large for one generation");
  const out = [];
  for (let i = 0; i < count; i++){
    const chunk = new Uint8Array(HEADER + mtu);
    chunk[0] = MAGIC0; chunk[1] = MAGIC1;
    chunk[2] = seq & 0xFF; chunk[3] = i; chunk[4] = count;
    chunk.set(stream.subarray(i * mtu, Math.min((i + 1) * mtu, stream.length)), HEADER);
    out.push(chunk);
  }
  return out;
}

class Reassembler {
  constructor(){ this._seq = null; this._count = 0; this._mtu = 0; this._frags = new Map(); }
  /* Feed one MSD payload (company ID stripped). Returns Uint8Array stream on
     completion (truncated to framed length per spec section 5.3), else null. */
  feed(msd){
    if (msd.length < HEADER + 1 || msd[0] !== MAGIC0 || msd[1] !== MAGIC1) return null;
    const seq = msd[2], idx = msd[3], cnt = msd[4];
    if (cnt === 0 || idx >= cnt) return null;
    if (seq !== this._seq){
      this._seq = seq; this._count = cnt; this._mtu = msd.length - HEADER;
      this._frags = new Map();
    } else if (cnt !== this._count || (msd.length - HEADER) !== this._mtu){
      /* poisoned generation (spec §5.3): drop ALL buffered fragments — an
         inconsistent fragment implies a different object sharing this seq.
         Buffer re-arms on the next fragment; the cyclic stream heals. */
      this._seq = null; this._count = 0; this._mtu = 0; this._frags = new Map();
      return null;
    }
    this._frags.set(idx, msd.subarray(HEADER));
    if (this._frags.size < this._count) return null;
    const buf = new Uint8Array(this._count * this._mtu);
    for (let i = 0; i < this._count; i++) buf.set(this._frags.get(i), i * this._mtu);
    this._frags = new Map();
    const clen = new DataView(buf.buffer).getUint32(0);
    if (clen > 65535 + 85) return null;
    const total = Math.ceil((8 + clen) / 32) * 32;
    if (total > buf.length) return null;
    return buf.slice(0, total);
  }
}

function packPdu(msd){
  const payload = new Uint8Array(3 + 2 + 2 + msd.length);
  payload.set([0x02, 0x01, 0x06], 0);
  payload[3] = 1 + 2 + msd.length; payload[4] = 0xFF;
  payload[5] = COMPANY & 0xFF; payload[6] = COMPANY >> 8;
  payload.set(msd, 7);
  if (payload.length > 31) throw new Error("legacy adv payload too large: " + payload.length);
  return payload;
}

function unpackPdu(payload){
  let off = 0;
  while (off + 2 <= payload.length){
    const ln = payload[off], type = payload[off + 1];
    const body = payload.subarray(off + 2, off + 1 + ln);
    if (body.length !== ln - 1) return null;
    if (type === 0xFF && body.length >= 2 + HEADER) return body.slice(2);
    off += 1 + ln;
  }
  return null;
}

return { COMPANY, LEGACY_MTU, EXTENDED_MTU, HEADER, fragment, Reassembler, packPdu, unpackPdu };
})();
if (typeof module !== "undefined") module.exports = SVBLE;
