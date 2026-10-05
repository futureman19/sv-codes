// svctest_ble.js — JS BMP-BLE receiver vs Python reference vectors (parity proof).
global.SVC = require('../../docs/js/svc.js');
const SVBLE = require('../../docs/js/ble.js');
const fs = require('fs');
const V = JSON.parse(fs.readFileSync('vectors/ble_vectors.json', 'utf8'));

const hex = (u8) => Array.from(u8).map(b => b.toString(16).padStart(2, '0')).join('');
const unhex = (h) => Uint8Array.from(Buffer.from(h, 'hex'));
let pass = 0, fail = 0;
function ok(cond, name){ if (cond) pass++; else { fail++; console.log('FAIL: ' + name); } }

const A = V.vector_a, B = V.vector_b, C = V.vector_c;

// 1. fragment() parity: JS output must equal Python's fragments byte-for-byte
const jsA = SVBLE.fragment(unhex(A.stream_hex), A.stream_seq, V.legacy_mtu).map(hex);
ok(JSON.stringify(jsA) === JSON.stringify(A.fragments_hex), 'JS fragment() == Python fragments (vector A)');
const jsB = SVBLE.fragment(unhex(B.stream_hex), B.stream_seq, V.extended_mtu).map(hex);
ok(JSON.stringify(jsB) === JSON.stringify(B.fragments_hex), 'JS fragment() == Python fragments (vector B)');

// 2. full-set reassembly -> stream -> envelope -> signature verify
let r = new SVBLE.Reassembler(), got = null;
for (const fh of A.fragments_hex) got = r.feed(unhex(fh)) || got;
ok(got && hex(got) === A.stream_hex, 'vector A reassembles');
const content = SVC.parseStream(got);
ok(hex(content) === A.envelope_hex, 'vector A envelope byte-identical after radio');
const env = SVC.parseEnvelope(content);
ok(SVC.ecdsaVerify(SVC.parsePubkey(V.authority_pubkey_compressed), env.signature, SVC.envelopeDigest(content)),
   'vector A signature verifies (golden authority)');
ok(new TextDecoder().decode(env.payload) === A.payload_text, 'vector A payload text matches');

// 3. deterministic loss/shuffle schedule completes
r = new SVBLE.Reassembler(); got = null;
outer:
for (const cycle of A.loss_shuffle_cycles_hex){
  for (const fh of cycle){ got = r.feed(unhex(fh)) || got; if (got) break outer; }
}
ok(got && hex(got) === A.stream_hex, 'loss/shuffle schedule completes');

// 4. generation change discards stale partial
r = new SVBLE.Reassembler();
for (const fh of C.stale_fragments_hex) r.feed(unhex(fh));
got = null;
for (const fh of C.fragments_hex) got = r.feed(unhex(fh)) || got;
ok(got && hex(got) === C.expected_stream_hex, 'vector C stale generation discarded');
const envC = SVC.parseEnvelope(SVC.parseStream(got));
ok(new TextDecoder().decode(envC.payload) === C.expected_payload_text, 'vector C payload = RESUME');

// 5. malformed PDUs
r = new SVBLE.Reassembler();
ok(r.feed(new Uint8Array(0)) === null, 'empty PDU dropped');
ok(r.feed(unhex('5858' + A.fragments_hex[0].slice(4))) === null, 'bad magic dropped');
const badCnt = unhex(A.fragments_hex[0]); badCnt[4] = 0;
ok(r.feed(badCnt) === null, 'zero Frag_Count dropped');
const badIdx = unhex(A.fragments_hex[0]); badIdx[3] = 99;
ok(r.feed(badIdx) === null, 'out-of-range Frag_Index dropped');
r.feed(unhex(A.fragments_hex[0]));
const badMix = unhex(A.fragments_hex[1]); badMix[4] = unhex(A.fragments_hex[0])[4] + 1;
ok(r.feed(badMix) === null, 'inconsistent generation count dropped');

// 6. on-air PDU parity
ok(hex(SVBLE.packPdu(unhex(A.fragments_hex[0]))) === A.onair_pdu0_hex, 'packPdu == Python on-air bytes');
ok(hex(SVBLE.unpackPdu(unhex(A.onair_pdu0_hex))) === A.fragments_hex[0], 'unpackPdu roundtrip');
ok(SVBLE.unpackPdu(new Uint8Array(31)) === null, 'non-BMP adv payload returns null');

// 7. extended single-PDU roundtrip
r = new SVBLE.Reassembler();
const gotB = r.feed(unhex(B.fragments_hex[0]));
ok(gotB && hex(gotB) === B.stream_hex, 'extended single-PDU reassembles');

// 8. poisoned-generation rule (spec §5.3) — mirrors Python test_ble.py
const frA = A.fragments_hex.map(unhex);
// (a) count mismatch poisons the whole generation
r = new SVBLE.Reassembler();
for (const f of frA.slice(0, 3)) r.feed(f);
const poison1 = unhex(A.fragments_hex[3]); poison1[4] = poison1[4] + 1;
ok(r.feed(poison1) === null, 'poison fragment (count) dropped');
got = null;
for (const f of frA.slice(3)) got = r.feed(f) || got;
ok(got === null, 'poisoned generation fully discarded (count)');
got = null;
for (const f of frA) got = r.feed(f) || got;
ok(got && hex(got) === A.stream_hex, 'self-heal after count poison');
// (b) mtu mismatch poisons the whole generation
r = new SVBLE.Reassembler();
r.feed(frA[0]); r.feed(frA[1]);
ok(r.feed(frA[2].slice(0, -3)) === null, 'poison fragment (mtu) dropped');
got = null;
for (const f of frA.slice(2)) got = r.feed(f) || got;
ok(got === null, 'poisoned generation fully discarded (mtu)');
got = null;
for (const f of frA) got = r.feed(f) || got;
ok(got && hex(got) === A.stream_hex, 'self-heal after mtu poison');
// (c) duplicates are harmless
r = new SVBLE.Reassembler(); got = null;
for (const f of [frA[0], frA[0], frA[1], frA[1], frA[2], frA[0], ...frA]) got = r.feed(f) || got;
ok(got && hex(got) === A.stream_hex, 'duplicates harmless');

console.log(`${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
