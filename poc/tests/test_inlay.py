"""SV-0005 QR-inlay matrix test suite.

Covers: layout resolution, frame packing, dense fountain-mode end-to-end
through the vision pipeline, distorted renders, the QR layer itself,
slot-erasure robustness, and inlay purity (payload never touches the QR).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from svcode.crypto import key_from_hex, pubkey_hex, sha256, vk_from_hex
from svcode.envelope import Envelope
from svcode.fountain import LTDecoder
from svcode.inlay import (
    HEADER_BITS,
    INNER,
    OFFSET,
    InlayDecoder,
    decode_inlay_image,
    encode_inlay_frame,
    layout_for,
    pack_inlay,
    render_inlay,
    unpack_inlay,
)

QR_PAYLOAD = "HTTPS://SVCODE.ORG"
GOLDEN_KEY_HEX = sha256(b"SV-0001 golden test vector authority").hex()
GOLDEN_NONCE = 1791504000


def golden_envelope(text: str) -> Envelope:
    env = Envelope(target_id=0x53564331, action=0x00FF, payload=text.encode(),
                   nonce=GOLDEN_NONCE)
    env.sign(key_from_hex(GOLDEN_KEY_HEX))
    return env


@pytest.fixture(scope="module")
def layout():
    return layout_for(QR_PAYLOAD)


# ---------- layout & packing ----------

def test_canonical_layout(layout):
    assert layout.qcells == 29        # v2 (25 modules) + 2-module border
    assert layout.inlay == 29
    assert layout.inlay0 == (INNER - 29) // 2
    assert layout.nslots >= 10        # at least today's static budget


def test_pack_unpack_roundtrip(layout):
    symbols = [bytes([i] * 32) for i in range(layout.nslots)]
    bits = pack_inlay(symbols, seed=1, ctype=0x01, k=7, layout=layout)
    assert len(bits) == len(layout.usable_cells)
    seed, ctype, k, out = unpack_inlay(bits, layout)
    assert (seed, ctype, k) == (1, 0x01, 7)
    assert out == symbols


def test_identity_seed_rejected(layout):
    env = golden_envelope("inlay")
    with pytest.raises(Exception):
        encode_inlay_frame(env.serialize(), layout, seed=0)


# ---------- end-to-end through the vision pipeline ----------

def _roundtrip(layout, text: str):
    env = golden_envelope(text)
    bits = encode_inlay_frame(env.serialize(), layout, seed=1)
    img = np.array(render_inlay(bits, layout, scale=10))[:, :, ::-1]  # RGB->BGR
    dec_bits = decode_inlay_image(img, layout)
    assert dec_bits == bits[: len(dec_bits)]
    dec = InlayDecoder()
    content = dec.feed_bits(dec_bits, layout)
    assert content is not None
    env2 = Envelope.parse(content)
    assert env2.verify(vk_from_hex(pubkey_hex(key_from_hex(GOLDEN_KEY_HEX))))
    assert env2.payload == text.encode()


def test_static_image_roundtrip(layout):
    _roundtrip(layout, "ONE CODE. Your camera read the QR.")


def test_distorted_image_decode(layout):
    env = golden_envelope("distortion check")
    bits = encode_inlay_frame(env.serialize(), layout, seed=1)
    img = np.array(render_inlay(bits, layout, scale=10))[:, :, ::-1]
    rng = np.random.default_rng(42)
    h, w = img.shape[:2]
    for _ in range(4):
        canvas = np.full((960, 1280, 3), 24, dtype=np.uint8)
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        jitter = rng.uniform(-40, 40, size=(4, 2)).astype(np.float32)
        dst = np.float32([[220, 130], [860, 90], [900, 700], [180, 680]]) + jitter
        m = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(img, m, (1280, 960))
        mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (1280, 960))
        canvas[mask > 127] = warped[mask > 127]
        noise = rng.normal(0, 6, canvas.shape).astype(np.int16)
        photo = cv2.GaussianBlur(np.clip(canvas.astype(np.int16) + noise, 0, 255)
                                 .astype(np.uint8), (3, 3), 0)
        assert decode_inlay_image(photo, layout) == bits[: layout.frame_bits]


# ---------- QR layer ----------

def test_qr_layer_reads(layout):
    bits = encode_inlay_frame(golden_envelope("qr").serialize(), layout, seed=1)
    img = cv2.cvtColor(np.array(render_inlay(bits, layout, scale=12)), cv2.COLOR_RGB2BGR)
    det = cv2.QRCodeDetector()
    ok, infos, _, _ = det.detectAndDecodeMulti(img)
    if not ok or not any(infos):
        s = det.detectAndDecode(img)[0]
        infos = [s] if s else []
    assert QR_PAYLOAD in infos


# ---------- erasure robustness ----------

def test_every_second_slot_still_solves(layout):
    env = golden_envelope("redundancy")
    bits = encode_inlay_frame(env.serialize(), layout, seed=1)
    seed, _c, k, symbols = unpack_inlay(bits, layout)
    lt = LTDecoder(k)
    solved = None
    for slot in range(0, layout.nslots, 2):  # half the slots destroyed
        if lt.add_frame_symbol(seed, slot, symbols[slot]):
            solved = lt.solved()
            if solved:
                break
    assert solved is not None, "fountain failed with every 2nd slot erased"
    from svcode.stream import parse_stream
    env2 = Envelope.parse(parse_stream(b"".join(solved)))
    assert env2.verify(vk_from_hex(pubkey_hex(key_from_hex(GOLDEN_KEY_HEX))))


# ---------- inlay purity ----------

def test_payload_never_touches_inlay(layout):
    ones = [1] * (HEADER_BITS + layout.nslots * 256)
    bits = ones + [0] * (len(layout.usable_cells) - len(ones))
    img = np.array(render_inlay(bits, layout, scale=4))
    s = 4
    x0 = (OFFSET + layout.inlay0) * s
    x1 = (OFFSET + layout.inlay0 + layout.inlay) * s
    plate = img[x0:x1, x0:x1]
    # inside the inlay, only QR modules are dark; count must match the QR exactly
    dark_expected = sum(row.count(True) for row in layout.qmat) * layout.qr_scale ** 2
    dark_cells = int((plate.reshape(layout.inlay, s, layout.inlay, s, 3)
                     .mean(axis=(1, 3)).max(axis=-1) < 128).sum())
    assert dark_cells == dark_expected
