"""make_ble_vectors.py — BMP-0001 reference vectors for cross-implementation tests.

Writes poc/vectors/ble_vectors.json: Python-generated streams and fragment sets
(plus a deterministic loss/shuffle delivery schedule) that any independent
BMP-BLE receiver must reassemble identically, ending in a verified envelope.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from svcode import ble
from svcode.crypto import key_from_hex, pubkey_hex
from svcode.envelope import Envelope
from svcode.stream import build_stream

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "vectors" / "ble_vectors.json"

GOLDEN_PRIV = "1fbf0a5d03e1b7db0ef88a9d107d143e8bc2710e4e9ae656956e0f948037f1ba"


def signed(msg: bytes) -> Envelope:
    env = Envelope(target_id=0x53564331, action=0x00FF, payload=msg)
    env.sign(key_from_hex(GOLDEN_PRIV))
    return env


def main() -> int:
    # Vector A: legacy profile, golden-signed message
    env_a = signed(b"HELLO OVER BLUETOOTH. This command traveled as radio, no pairing.")
    stream_a = build_stream(env_a.serialize())
    frags_a = ble.fragment(stream_a, stream_seq=3)

    # Vector B: extended profile, single fragment
    env_b = signed(b"GO")
    stream_b = build_stream(env_b.serialize())
    frags_b = ble.fragment(stream_b, stream_seq=1, mtu=ble.EXTENDED_MTU)
    assert len(frags_b) == 1

    # Deterministic loss/shuffle delivery schedule for vector A (seeded RNG):
    # cycles of fragment hexes to feed, in order — reproducible anywhere.
    # Generate cycles until the surviving fragments cover every index.
    rng = random.Random(42)
    schedule = []
    covered: set[int] = set()
    for _ in range(6):
        order = frags_a[:]
        rng.shuffle(order)
        cycle = [f for f in order if rng.random() >= 0.4]
        covered.update(f[3] for f in cycle)
        schedule.append([f.hex() for f in cycle])
        if len(covered) == len(frags_a):
            break
    assert len(covered) == len(frags_a), "rng schedule never covers the set"

    # Vector C: two generations (stale partial must be discarded)
    env_c1 = signed(b"HALT")
    env_c2 = signed(b"RESUME")
    stream_c1, stream_c2 = build_stream(env_c1.serialize()), build_stream(env_c2.serialize())
    frags_c1 = ble.fragment(stream_c1, stream_seq=3)
    frags_c2 = ble.fragment(stream_c2, stream_seq=4)

    vectors = {
        "warning": "BMP-0001 reference vectors — test-only authority key, never for production",
        "authority_pubkey_compressed": pubkey_hex(key_from_hex(GOLDEN_PRIV)),
        "legacy_mtu": ble.LEGACY_MTU,
        "extended_mtu": ble.EXTENDED_MTU,
        "vector_a": {
            "profile": "LE-Legacy", "stream_seq": 3,
            "payload_text": env_a.payload.decode(),
            "envelope_hex": env_a.serialize().hex(),
            "stream_hex": stream_a.hex(),
            "fragments_hex": [f.hex() for f in frags_a],
            "onair_pdu0_hex": ble.pack_pdu(frags_a[0]).hex(),
            "loss_shuffle_cycles_hex": schedule,
        },
        "vector_b": {
            "profile": "LE-Extended", "stream_seq": 1,
            "payload_text": env_b.payload.decode(),
            "envelope_hex": env_b.serialize().hex(),
            "stream_hex": stream_b.hex(),
            "fragments_hex": [f.hex() for f in frags_b],
        },
        "vector_c": {
            "note": "feed first two fragments of generation 3, then all of generation 4; "
                    "result must be stream_c2 (stale generation discarded)",
            "stale_fragments_hex": [f.hex() for f in frags_c1[:2]],
            "fragments_hex": [f.hex() for f in frags_c2],
            "expected_stream_hex": stream_c2.hex(),
            "expected_payload_text": env_c2.payload.decode(),
        },
    }
    OUT.write_text(json.dumps(vectors, indent=2))
    print(f"wrote {OUT}")
    print(f"vector A: {len(frags_a)} legacy fragments, stream {len(stream_a)}B")
    print(f"vector B: 1 extended fragment, stream {len(stream_b)}B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
