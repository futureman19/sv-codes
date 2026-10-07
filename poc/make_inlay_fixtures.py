"""make_inlay_fixtures.py — SV-0005 inlay fixtures for the JS decoder harness.

Writes raw RGBA "camera photos" (clean + distorted) of inlay codes signed by
the golden test authority, plus meta.json with expected bits. The node
harness (svctest_inlay.js) decodes them with docs/js/decoder.js and asserts
bit-exact equality + full stream decode + signature verify — same pattern as
make_fixtures.py / svctest_decoder.js.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from svcode.crypto import key_from_hex, pubkey_hex, sha256
from svcode.envelope import Envelope
from svcode.inlay import encode_inlay_frame, layout_for, render_inlay

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures_inlay"
QR_PAYLOAD = "HTTPS://SVCODE.ORG"

GOLDEN_KEY_HEX = sha256(b"SV-0001 golden test vector authority").hex()
GOLDEN_NONCE = 1791504000


def save_rgba(rgb: np.ndarray, path: Path) -> None:
    alpha = np.full((*rgb.shape[:2], 1), 255, dtype=np.uint8)
    path.write_bytes(np.concatenate([rgb, alpha], axis=2).tobytes())


def bits_hex(bits: list[int]) -> str:
    out = bytearray(len(bits) // 8)
    for i, b in enumerate(bits):
        if b:
            out[i >> 3] |= 0x80 >> (i & 7)
    return bytes(out).hex()


def distort(rgb: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    h, w = rgb.shape[:2]
    canvas = np.full((960, 1280, 3), 24, dtype=np.uint8)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    jitter = rng.uniform(-40, 40, size=(4, 2)).astype(np.float32)
    dst = np.float32([[220, 130], [860, 90], [900, 700], [180, 680]]) + jitter
    m = cv2.getPerspectiveTransform(src, dst)
    bgr = rgb[:, :, ::-1]
    warped = cv2.warpPerspective(bgr, m, (1280, 960))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (1280, 960))
    canvas[mask > 127] = warped[mask > 127]
    noise = rng.normal(0, 6, canvas.shape).astype(np.int16)
    canvas = np.clip(canvas.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(canvas, (3, 3), 0)[:, :, ::-1]  # back to RGB


def envelope(text: str) -> Envelope:
    env = Envelope(target_id=0x53564331, action=0x00FF, payload=text.encode(),
                   nonce=GOLDEN_NONCE)
    env.sign(key_from_hex(GOLDEN_KEY_HEX))
    return env


def main() -> None:
    FIXTURES.mkdir(exist_ok=True)
    layout = layout_for(QR_PAYLOAD)
    sk = key_from_hex(GOLDEN_KEY_HEX)
    meta = {
        "format": "SV-0005 inlay (96x96, canonical 29-cell inlay)",
        "qr_payload": QR_PAYLOAD,
        "frame_bits": layout.frame_bits,
        "authority_pubkey": pubkey_hex(sk),
        "cases": [],
    }
    rng = np.random.default_rng(11)

    cases = [
        ("inlay_clean", "HELLO, INLAY.", False),
        ("inlay_skew1", "HELLO, INLAY.", True),
        ("inlay_skew2", "HELLO, INLAY.", True),
        ("inlay_big", "SV-0005 dense fountain fill. " * 12, False),  # K > 10
    ]
    for name, text, do_distort in cases:
        env = envelope(text)
        bits = encode_inlay_frame(env.serialize(), layout, seed=1)
        img = np.array(render_inlay(bits, layout, scale=10))  # RGB
        if do_distort:
            img = distort(img, rng)
        fn = f"{name}.rgba"
        save_rgba(img, FIXTURES / fn)
        meta["cases"].append({
            "file": fn, "width": int(img.shape[1]), "height": int(img.shape[0]),
            "expect_bits_hex": bits_hex(bits[: layout.frame_bits]),
            "payload": text, "k": (8 + len(env.serialize()) + 31) // 32,
        })
        print(f"wrote {fn} K={meta['cases'][-1]['k']} distort={do_distort}")

    (FIXTURES / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"meta.json -> {FIXTURES} ({len(meta['cases'])} cases)")


if __name__ == "__main__":
    main()
