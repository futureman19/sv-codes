"""Generate vision fixtures for the JS decoder test (poc/fixtures/).

Each fixture is a synthetic 'camera photo' of a rendered SV Code frame:
perspective-skewed onto a dark canvas, with gaussian noise + blur — saved as
raw RGBA bytes + meta.json. The node test decodes them with docs/js/decoder.js
and asserts bit-exact equality with the Python-known bits.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import cv2
import numpy as np

from svcode.codec import Encoder
from svcode.crypto import key_from_hex, sha256
from svcode.envelope import Envelope
from svcode.render import render_frame

ROOT = Path(__file__).parent
FIXTURES = ROOT / "fixtures"

GOLDEN_KEY_HEX = sha256(b"SV-0001 golden test vector authority").hex()
GOLDEN_NONCE = 1791504000


def distort(img_rgb: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    h, w = img_rgb.shape[:2]
    canvas = np.full((960, 1280, 3), 24, dtype=np.uint8)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    jitter = rng.uniform(-40, 40, size=(4, 2)).astype(np.float32)
    dst = np.float32([[220, 130], [860, 90], [900, 700], [180, 680]]) + jitter
    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img_rgb, m, (1280, 960))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (1280, 960))
    canvas[mask > 127] = warped[mask > 127]
    noise = rng.normal(0, 6, canvas.shape).astype(np.int16)
    canvas = np.clip(canvas.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(canvas, (3, 3), 0)


def save_rgba(rgb: np.ndarray, path: Path) -> None:
    alpha = np.full((*rgb.shape[:2], 1), 255, dtype=np.uint8)
    rgba = np.concatenate([rgb, alpha], axis=2)
    path.write_bytes(rgba.tobytes())


def main() -> int:
    FIXTURES.mkdir(exist_ok=True)
    rng = np.random.default_rng(42)
    sk = key_from_hex(GOLDEN_KEY_HEX)
    meta = {"fixtures": []}

    # static vector
    env1 = Envelope(target_id=0x53564331, action=0x00FF,
                    payload=b"HELLO, MACHINE.", nonce=GOLDEN_NONCE)
    env1.sign(sk)
    enc1 = Encoder(env1.serialize())
    _, bits1 = enc1.frame_bits(0)
    clean1 = np.array(render_frame(bits1, scale=10))

    for name, img in (("static_clean", clean1), ("static_skew", distort(clean1, rng))):
        fn = f"{name}.rgba"
        save_rgba(img, FIXTURES / fn)
        meta["fixtures"].append({
            "file": fn, "width": img.shape[1], "height": img.shape[0],
            "expect_bits_hex": bytes(np.packbits(bits1)).hex(),
        })

    # fountain vector (2 frames suffice for K=11; include 3 for loss margin)
    params = struct.pack(">ii", 37774900, -122419400)
    payload = json.dumps({"note": "fixture", "pad": "x" * 240}).encode()
    env2 = Envelope(target_id=0x53564331, action=0x00A1, params=params,
                    payload=payload, nonce=GOLDEN_NONCE)
    env2.sign(sk)
    enc2 = Encoder(env2.serialize())
    assert not enc2.static

    stream_frames = []
    for seq in range(3):
        seed, bits = enc2.frame_bits(seq)
        img = distort(np.array(render_frame(bits, scale=10)), rng)
        fn = f"fountain_{seed}.rgba"
        save_rgba(img, FIXTURES / fn)
        stream_frames.append({
            "file": fn, "width": img.shape[1], "height": img.shape[0],
            "expect_bits_hex": bytes(np.packbits(bits)).hex(),
        })
    meta["fountain"] = {
        "frames": stream_frames,
        "expect_payload_hex": payload.hex(),
        "authority_pubkey": "02ac1b5e6915999ebbc89be7405a9fa297b0c549583a9cd3aaab750c2abc5aaeb1",
    }
    (FIXTURES / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {len(meta['fixtures']) + len(stream_frames)} fixtures to {FIXTURES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
