// svctest_l2l3.js — JS L2/L3 verifiers vs Python reference on the live mainnet
// vectors: byte-identical intermediates + identical accept/reject behavior.
global.SVC = require('../../docs/js/svc.js');
const SVANCHOR = require('../../docs/js/anchor.js');
const SVSPV = require('../../docs/js/spv.js');
const fs = require('fs');
const VDIR = 'vectors/';
const l2 = JSON.parse(fs.readFileSync(VDIR + 'l2_live.json', 'utf8'));
const l3 = JSON.parse(fs.readFileSync(VDIR + 'l3_live.json', 'utf8'));
const ref = JSON.parse(fs.readFileSync('js_tests/l2l3_ref.json', 'utf8'));

const unhex = (h) => Uint8Array.from(Buffer.from(h, 'hex'));
const hex = (b) => Buffer.from(b).toString('hex');
let pass = 0, fail = 0;
function ok(cond, name){ if (cond) pass++; else { fail++; console.log('FAIL: ' + name); } }
function throws(fn, match, name){
  try { fn(); fail++; console.log('FAIL (no throw): ' + name); }
  catch (e) { ok(e.message.includes(match), name + ` [${e.message.slice(0, 60)}]`); }
}

/* ---------- RIPEMD-160 port self-test (canonical vectors) ---------- */
ok(hex(SVANCHOR.ripemd160(new Uint8Array(0))) === '9c1185a5c5e9fc54612808977ee8f548b2258d31',
   'ripemd160("") canonical');
ok(hex(SVANCHOR.ripemd160(new TextEncoder().encode('abc'))) === '8eb208f7e05d987a9b044a8e98c6b087f15a0bfc',
   'ripemd160("abc") canonical');

/* ---------- L2: parse parity ---------- */
const raw = unhex(l2.raw_tx_hex);
const tx = SVANCHOR.parseTx(raw);
ok(tx.txid === ref.l2.txid, 'parseTx txid');
ok(tx.version === ref.l2.version && tx.locktime === ref.l2.locktime, 'version/locktime');
ok(tx.inputs.length === ref.l2.n_inputs && tx.outputs.length === ref.l2.n_outputs, 'input/output counts');
ok(Number(tx.outputs[0].value) === ref.l2.output0_value &&
   Number(tx.outputs[1].value) === ref.l2.output1_value, 'output values');

/* ---------- L2: sighash byte-identical ---------- */
const prevScript = unhex(l2.prevouts[0].script_hex);
const structured = tx.inputs.map(i => ({ outpoint: i.outpoint, sequence: i.sequence }));
const digest = SVANCHOR.sighashForkid(structured, tx.outputs, 0, prevScript, l2.prevouts[0].value,
                                      0x41, tx.version, tx.locktime);
ok(hex(digest) === ref.l2.sighash_input0_hex, 'sighash_forkid byte-identical');

/* ---------- L2: extract + verify ---------- */
ok(hex(SVANCHOR.extractEnvelope(raw)) === ref.l2.envelope_hex, 'extractEnvelope byte-identical');
const seen = new Map();
const env = SVANCHOR.verifyL2(raw, l2.prevouts, l2.authority_pubkey, seen);
ok(new TextDecoder().decode(env.payload) === l2.payload_text, 'verifyL2 PASS + payload');
ok(seen.size === 1 && [...seen.values()][0] === l2.txid, 'freshness recorded');

/* ---------- L2: rejection parity ---------- */
const V1 = JSON.parse(fs.readFileSync(VDIR + 'vectors.json', 'utf8'));
const badEnv = unhex(l2.raw_tx_hex);  // flip last payload byte inside the tx copy
{
  // easier: corrupt the envelope hex before anchoring is Python-side; here flip a sig byte in raw
  const i = l2.raw_tx_hex.indexOf(l2.envelope_hex.slice(42, 42 + 16)); // inside sig region
  badEnv[i >>> 1] ^= 0xFF;
  throws(() => SVANCHOR.verifyL2(badEnv, l2.prevouts, l2.authority_pubkey, new Map()),
         'envelope signature invalid', 'corrupt envelope sig rejected');
}
throws(() => SVANCHOR.verifyL2(raw, [], l2.authority_pubkey, new Map()),
       'missing prevout evidence', 'missing evidence rejected');
{
  const forged = [{ ...l2.prevouts[0], value: l2.prevouts[0].value * 100 }];
  throws(() => SVANCHOR.verifyL2(raw, forged, l2.authority_pubkey, new Map()),
         'signature invalid', 'forged prevout value rejected');
}
throws(() => SVANCHOR.verifyL2(raw, l2.prevouts, V1 ? l2.authority_pubkey.slice(0, 2) === '02'
        ? '03' + l2.authority_pubkey.slice(2) : '02' + l2.authority_pubkey.slice(2) : '', new Map()),
       'envelope signature invalid', 'wrong authority rejected');
{
  const seen2 = new Map(); seen2.set(hex(tx.inputs[0].outpoint), 'ff'.repeat(32));
  throws(() => SVANCHOR.verifyL2(raw, l2.prevouts, l2.authority_pubkey, seen2),
         'double-spend', 'double-spend freshness rejected');
}

/* ---------- L3: BEEF/BUMP/header parity ---------- */
const beef = unhex(l3.beef_hex);
const doc = SVSPV.parseBeef(beef);
ok(doc.bumps.length === ref.l3.n_bumps && doc.txs.length === ref.l3.n_txs, 'parseBeef counts');
ok(doc.txs[1].txid === ref.l3.subject_txid && doc.txs[0].txid === ref.l3.parent_txid, 'BEEF txids');
ok(hex(SVSPV.bumpRoot(doc.bumps[0], doc.txs[0].txid)) === ref.l3.bump0_root_internal_hex,
   'bumpRoot(parent) byte-identical');
ok(hex(SVSPV.bumpRoot(doc.bumps[1], doc.txs[1].txid)) === ref.l3.bump1_root_internal_hex,
   'bumpRoot(subject) byte-identical');

const headers = [unhex(l3.subject_block.header_hex), unhex(l3.parent_block.header_hex)];
const h0 = SVSPV.verifyHeader(headers[0]);
ok(h0.hash === l3.subject_block.blockhash, 'header hash == WoC blockhash');
ok(h0.hash === ref.l3.subject_header_hash, 'header hash == Python');

const env3 = SVSPV.verifyL3(beef, l3.authority_pubkey, headers, new Map(), l3.tip_height_at_fetch, 1);
ok(new TextDecoder().decode(env3.payload) === l3.expected_payload, 'verifyL3 PASS + payload');

/* ---------- L3: rejection parity ---------- */
{
  const bad = unhex(l3.beef_hex); bad[60] ^= 0xFF;
  throws(() => SVSPV.verifyL3(bad, l3.authority_pubkey, headers, new Map(), l3.tip_height_at_fetch),
         '', 'corrupt BUMP rejected');
}
{
  const bad = unhex(l3.subject_block.header_hex); bad[10] ^= 0xFF;
  throws(() => SVSPV.verifyL3(beef, l3.authority_pubkey, [bad, headers[1]], new Map(), l3.tip_height_at_fetch),
         'proof-of-work', 'corrupt header rejected');
}
// both txs share block 969795 → same header; empty store = missing header
throws(() => SVSPV.verifyL3(beef, l3.authority_pubkey, [], new Map(), l3.tip_height_at_fetch),
       'merkle root not in header store', 'missing header rejected');
throws(() => SVSPV.verifyL3(beef, l3.authority_pubkey, headers, new Map(), l3.tip_height_at_fetch, l3.tip_height_at_fetch + 10),
       'insufficient burial depth', 'depth policy enforced');

console.log(`${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
