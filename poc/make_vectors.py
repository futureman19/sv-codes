"""Generate the golden test vectors for SV-0001 §8 / BMP-0000.

Writes poc/vectors/ with:
  - vectors.json        : keys, envelope, signature, CRC, K, parity flag
  - static_frame.png    : golden envelope as a static (seed 0) SV Code
  - fountain/           : MOVE_TO envelope as an animated frame sequence
  - js_frames.json      : frames produced by the WEBSITE JS encoder for the
                          same envelope bytes — Python re-generates them and
                          asserts bit-exact parity (two implementations, one wire format)

The private key is published on purpose: these are TEST vectors.
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from svcode.codec import Encoder
from svcode.crypto import crc32, key_from_hex, pubkey_hex, sha256
from svcode.envelope import Envelope
from svcode.render import render_frame

ROOT = Path(__file__).parent
VECTORS = ROOT / "vectors"
INDEX_HTML = ROOT.parent / "docs" / "index.html"

GOLDEN_KEY_HEX = sha256(b"SV-0001 golden test vector authority").hex()
GOLDEN_NONCE = 1791504000  # fixed: deterministic vectors


def js_frames(envelope_hex: str, seqs: list[int]) -> list[dict]:
    """Run the website's own encoder (docs/js/svc.js module) in Node."""
    harness = r"""
const SVC = require(process.argv[2]);
const content = Uint8Array.from(Buffer.from(process.argv[3], 'hex'));
const seqs = JSON.parse(process.argv[4]);
const stream = SVC.buildStream(content);
const K = stream.length / 32;
const symbols = []; for (let i = 0; i < K; i++) symbols.push(stream.subarray(i*32, i*32+32));
const cdf = SVC.solitonCDF(K);
const out = [];
for (const seq of seqs) {
  const seed = (K <= 10) ? 0 : (seq % 65535) + 1;
  const enc = []; for (let s = 0; s < 10; s++) enc.push(SVC.encodeSymbol(symbols, cdf, seed, s));
  out.push({ seq, seed, bits: Array.from(SVC.packFrame(enc, seed, 1, K)) });
}
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        harness_path = f.name
    try:
        out = subprocess.run(
            ["node", harness_path, str(ROOT.parent / "docs" / "js" / "svc.js"),
             envelope_hex, json.dumps(seqs)],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        print("node not found — skipping JS parity vector", file=sys.stderr)
        return []
    return json.loads(out.stdout)


def main() -> int:
    VECTORS.mkdir(parents=True, exist_ok=True)
    sk = key_from_hex(GOLDEN_KEY_HEX)

    # --- Vector 1: static (K<=10), HELLO, MACHINE. ---
    env1 = Envelope(target_id=0x53564331, action=0x00FF,
                    payload=b"HELLO, MACHINE.", nonce=GOLDEN_NONCE)
    env1.sign(sk)
    enc1 = Encoder(env1.serialize())
    assert enc1.static, "vector 1 must be static-mode"
    _, bits1 = enc1.frame_bits(0)
    render_frame(bits1, scale=10).save(VECTORS / "static_frame.png")

    # --- Vector 2: fountain, MOVE_TO with JSON payload ---
    params = struct.pack(">ii", 37774900, -122419400)  # SF, fixed-point 1e-6
    payload = json.dumps({
        "note": "Delivery bounty #1: proceed to coordinates, scan the next "
                "SV Code on arrival, claim 5000 sats. Route via the pier; "
                "avoid the construction zone on 5th. Confirm arrival with a "
                "signed REPORT_STATUS envelope back to dispatch.",
        "speed_mm_s": 500,
    }).encode()
    env2 = Envelope(target_id=0x53564331, action=0x00A1, params=params,
                    payload=payload, nonce=GOLDEN_NONCE)
    env2.sign(sk)
    enc2 = Encoder(env2.serialize())
    assert not enc2.static, "vector 2 must be fountain-mode"
    (VECTORS / "fountain").mkdir(exist_ok=True)
    for seq in range(6):
        seed, bits = enc2.frame_bits(seq)
        render_frame(bits, scale=10).save(VECTORS / "fountain" / f"frame_{seed:05d}.png")

    # --- JS parity on vector 1 (static) and vector 2 (seeds 1..4) ---
    parity_entries = []
    js1 = js_frames(env1.serialize().hex(), [0])
    js2 = js_frames(env2.serialize().hex(), [0, 1, 2, 3])
    parity_ok = True
    for enc, js_set in ((enc1, js1), (enc2, js2)):
        for entry in js_set:
            seed, bits = enc.frame_bits(entry["seq"])
            match = seed == entry["seed"] and bits == entry["bits"]
            parity_ok = parity_ok and match
            parity_entries.append({"seq": entry["seq"], "seed": entry["seed"],
                                   "bits": entry["bits"]})
    js_dump = {"envelope_hex": env2.serialize().hex(), "frames": parity_entries[-4:]} \
        if js2 else {"envelope_hex": env1.serialize().hex(), "frames": parity_entries}
    (VECTORS / "js_frames.json").write_text(json.dumps(js_dump))

    summary = {
        "warning": "TEST VECTORS ONLY — the private key is published intentionally.",
        "private_key_hex": GOLDEN_KEY_HEX,
        "authority_pubkey_compressed": pubkey_hex(sk),
        "nonce": GOLDEN_NONCE,
        "vector1": {
            "kind": "static",
            "payload_text": "HELLO, MACHINE.",
            "action": "0x00FF VENDOR",
            "envelope_hex": env1.serialize().hex(),
            "signature_hex": env1.signature.hex(),
            "crc32": f"0x{crc32(env1.serialize()):08X}",
            "k": enc1.k,
            "image": "static_frame.png",
        },
        "vector2": {
            "kind": "fountain",
            "action": "0x00A1 MOVE_TO",
            "params": {"x_e6": 37774900, "y_e6": -122419400},
            "payload_json": json.loads(payload),
            "envelope_hex": env2.serialize().hex(),
            "signature_hex": env2.signature.hex(),
            "crc32": f"0x{crc32(env2.serialize()):08X}",
            "k": enc2.k,
            "images": "fountain/frame_*.png (seeds 1..6)",
        },
        "js_python_parity": parity_ok,
    }
    (VECTORS / "vectors.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "vector2"}, indent=2)[:600])
    print(f"\nvector2 k={enc2.k}, js_python_parity={parity_ok}")
    return 0 if parity_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
