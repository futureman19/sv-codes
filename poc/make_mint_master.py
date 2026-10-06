"""Build the full-bleed SV-0003 demo master; never touches genesis-001 assets.

Run with poc/.venv/Scripts/python.exe poc/make_mint_master.py from any cwd.
The known demo issuer is NOT a production security identity. No network calls.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from make_genesis_001 import (ISSUER_SK, ISSUER_PUB, TARGET_GENESIS, canonical,
                              build_code_art, sword_reference, CELL, INNER, OFFSET)
from svcode.codec import Encoder, Decoder
from svcode.crypto import vk_from_hex
from svcode.decode import decode_file
from svcode.envelope import Envelope

ACTION_MINT_CLAIM = 0xC1A1
OUTPUT = Path(__file__).resolve().parents[1] / "docs/nft/genesis/mint"
CERT = {"col": "sv-genesis", "endpoint": "https://sv-mint.fly.dev", "exp": 0,
        "price": 0, "supply": 100, "v": 3}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = canonical(CERT)
    assert len(payload) <= 227, f"certificate exceeds static budget: {len(payload)}B"
    # An inert perpetual claim pointer, not a replay-protected transaction.
    # Fixed nonce makes the poster reproducible, independent of build time.
    env = Envelope(target_id=TARGET_GENESIS, action=ACTION_MINT_CLAIM,
                   nonce=0, payload=payload)
    env.sign(ISSUER_SK)
    serialized = env.serialize()
    encoder = Encoder(serialized)
    assert encoder.static, "master must fit one static frame"
    _, bits = encoder.frame_bits(0)
    png = OUTPUT / "mint-master-code.png"
    jpg = OUTPUT / "mint-master-code.jpg"
    build_code_art(bits, str(png))
    # Master posters must survive small, blurred phone-camera scenes. Enlarge
    # bit-one ink from the collectible's 10px minimum to 14px, retaining the
    # blade's full-cell silhouette. Touch payload cells only, never anchors.
    with Image.open(png) as original:
        image = original.convert("RGB")
    draw = ImageDraw.Draw(image)
    reference = sword_reference()
    for i, bit in enumerate(bits):
        if not bit:
            continue
        r, c = divmod(i, INNER)
        blade = reference[r][c] >= 1.0
        side = CELL if blade else 14
        inset = (CELL - side) // 2
        x, y = (c + OFFSET) * CELL + inset, (r + OFFSET) * CELL + inset
        draw.rectangle((x, y, x + side - 1, y + side - 1),
                       fill=(18, 22, 34) if blade else (52, 62, 84))
    image.save(png)
    with Image.open(png) as image:
        image.convert("RGB").save(jpg, quality=80, subsampling=0)
    receipts = []
    for path in (png, jpg):
        recovered_bits = decode_file(str(path))
        content = Decoder().feed_bits(recovered_bits)
        assert content is not None, f"incomplete stream: {path.name}"
        decoded = Envelope.parse(content)
        assert decoded.verify(vk_from_hex(ISSUER_PUB)), "invalid signature"
        assert decoded.payload == payload, "certificate mismatch"
        assert decoded.action == ACTION_MINT_CLAIM and decoded.target_id == TARGET_GENESIS
        assert content == serialized, "envelope mismatch"
        errors = sum(a != b for a, b in zip(bits, recovered_bits))
        receipt = {"file": path.name, "signature": "VALID", "certificate": "MATCH",
                   "envelope": "MATCH", "bit_errors": errors,
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        receipts.append(receipt)
        print(json.dumps(receipt))
    meta = {"cert": CERT, "cert_bytes": len(payload),
            "cert_sha256": hashlib.sha256(payload).hexdigest(),
            "issuer_pub": ISSUER_PUB, "action": ACTION_MINT_CLAIM,
            "target_id": TARGET_GENESIS, "envelope": serialized.hex(),
            "static": encoder.static, "nonce": 0, "python_verification": receipts,
            "warning": "Public demo issuer key; not production anti-forgery security."}
    (OUTPUT / "mint-master-cert.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"master cert {len(payload)}B <= 227B; action 0xC1A1; target GEN1; static frame")
    print(OUTPUT)


if __name__ == "__main__":
    main()
