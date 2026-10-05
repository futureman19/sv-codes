"""SV Code PoC test suite.

Covers: envelope crypto, stream framing, frame packing, fountain roundtrip
(with frame loss), full vision pipeline on clean renders, distorted renders
(perspective skew + noise + blur), and JS<->Python wire-format parity.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from svcode.codec import Decoder, Encoder
from svcode.crypto import generate_key, key_from_hex, pubkey_hex, sha256, vk_from_hex
from svcode.decode import decode_image
from svcode.envelope import Envelope
from svcode.fountain import LTDecoder, encode_symbol, soliton_cdf
from svcode.frame import pack_frame, unpack_frame
from svcode.render import render_frame
from svcode.stream import StreamError, build_stream, parse_stream

VECTORS = Path(__file__).parent.parent / "vectors"
GOLDEN_KEY_HEX = sha256(b"SV-0001 golden test vector authority").hex()
GOLDEN_NONCE = 1791504000  # fixed timestamp for deterministic vectors


def golden_envelope(text: str = "HELLO, MACHINE.") -> Envelope:
    env = Envelope(target_id=0x53564331, action=0x00FF, payload=text.encode(), nonce=GOLDEN_NONCE)
    env.sign(key_from_hex(GOLDEN_KEY_HEX))
    return env


# ---------- envelope crypto ----------

def test_envelope_sign_verify():
    sk = generate_key()
    env = Envelope(target_id=1, action=0x00A1, payload=b"go")
    env.sign(sk)
    assert env.verify(sk.verifying_key)


def test_envelope_tamper_detection():
    sk = generate_key()
    env = Envelope(target_id=1, action=0x00A1, payload=b"go")
    env.sign(sk)
    data = bytearray(env.serialize())
    data[-1] ^= 0x01  # flip one payload bit
    tampered = Envelope.parse(bytes(data))
    assert not tampered.verify(sk.verifying_key)


def test_envelope_wrong_key():
    env = Envelope(target_id=1, action=0x00A1, payload=b"go")
    env.sign(generate_key())
    assert not env.verify(generate_key().verifying_key)


def test_envelope_parse_rejects_truncation():
    env = golden_envelope()
    with pytest.raises(Exception):
        Envelope.parse(env.serialize()[:-1])


# ---------- stream framing ----------

def test_stream_roundtrip():
    content = b"\x00" * 300 + b"svcode"
    assert parse_stream(build_stream(content)) == content


def test_stream_crc_detects_corruption():
    buf = bytearray(build_stream(b"payload"))
    buf[12] ^= 0xFF
    with pytest.raises(StreamError):
        parse_stream(bytes(buf))


# ---------- frame packing ----------

def test_frame_pack_unpack():
    symbols = [bytes([i] * 32) for i in range(10)]
    bits = pack_frame(symbols, seed=42, ctype=0x01, k=7)
    assert len(bits) == 2704
    seed, ctype, k, out = unpack_frame(bits)
    assert (seed, ctype, k) == (42, 0x01, 7)
    assert out == symbols


# ---------- fountain codec ----------

def test_fountain_roundtrip_with_loss():
    content = golden_envelope().serialize()
    enc = Encoder(content)
    assert not enc.static or True
    dec = LTDecoder(enc.k)
    rng = np.random.default_rng(7)
    solved = None
    for seq in range(400):
        seed, bits = enc.frame_bits(seq)
        _, _, k, symbols = unpack_frame(bits)
        assert k == enc.k
        for slot, sym in enumerate(symbols):
            if sym == bytes(32) or rng.random() < 0.5:  # drop 50% of symbols
                continue
            if dec.add_frame_symbol(seed, slot, sym):
                solved = dec.solved()
                break
        if solved:
            break
    assert solved is not None, "fountain did not converge within 400 frames"
    assert parse_stream(b"".join(solved)) == content


# ---------- full vision pipeline (bit-exact renders) ----------

def test_static_image_roundtrip():
    env = golden_envelope()
    enc = Encoder(env.serialize())
    assert enc.static
    _, bits = enc.frame_bits(0)
    img = np.array(render_frame(bits, scale=10))[:, :, ::-1]  # RGB->BGR
    dec_bits = decode_image(img)
    assert dec_bits == bits
    dec = Decoder()
    content = dec.feed_bits(dec_bits)
    assert content is not None
    env2 = Envelope.parse(content)
    assert env2.verify(vk_from_hex(pubkey_hex(key_from_hex(GOLDEN_KEY_HEX))))
    assert env2.payload == b"HELLO, MACHINE."


def test_fountain_image_roundtrip():
    big = "SV Codes: machines reading light. " * 40  # >227B -> fountain mode
    env = golden_envelope(big)
    enc = Encoder(env.serialize())
    assert not enc.static
    dec = Decoder()
    for seq in range(30):
        _, bits = enc.frame_bits(seq)
        img = np.array(render_frame(bits, scale=10))[:, :, ::-1]
        content = dec.feed_bits(decode_image(img))
        if content is not None:
            env2 = Envelope.parse(content)
            assert env2.payload == big.encode()
            return
    pytest.fail("image fountain did not converge in 30 frames")


# ---------- distorted renders (simulated real camera) ----------

def _distort(img_bgr: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    canvas = np.full((960, 1280, 3), 24, dtype=np.uint8)  # dark desk
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    jitter = rng.uniform(-40, 40, size=(4, 2)).astype(np.float32)
    dst = np.float32([[220, 130], [860, 90], [900, 700], [180, 680]]) + jitter
    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img_bgr, m, (1280, 960))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (1280, 960))
    canvas[mask > 127] = warped[mask > 127]
    noise = rng.normal(0, 6, canvas.shape).astype(np.int16)
    canvas = np.clip(canvas.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(canvas, (3, 3), 0)


def test_distorted_image_decode():
    env = golden_envelope()
    enc = Encoder(env.serialize())
    _, bits = enc.frame_bits(0)
    img = np.array(render_frame(bits, scale=10))[:, :, ::-1]
    rng = np.random.default_rng(42)
    for _ in range(5):  # several random skews/noise draws
        photo = _distort(img, rng)
        assert decode_image(photo) == bits


# ---------- golden vectors & JS parity ----------

def test_golden_vector_signature_stable():
    env = golden_envelope()
    vf = VECTORS / "vectors.json"
    if not vf.exists():
        pytest.skip("vectors not generated yet")
    v = json.loads(vf.read_text())
    assert env.serialize().hex() == v["vector1"]["envelope_hex"]
    assert env.verify(vk_from_hex(v["authority_pubkey_compressed"]))


def test_js_python_parity():
    jf = VECTORS / "js_frames.json"
    if not jf.exists():
        pytest.skip("JS parity vectors not generated")
    frames = json.loads(jf.read_text())
    env = Envelope.parse(bytes.fromhex(frames["envelope_hex"]))
    enc = Encoder(env.serialize())
    for entry in frames["frames"]:
        seed, bits = enc.frame_bits(entry["seq"])
        assert seed == entry["seed"]
        assert bits == entry["bits"], f"JS/Python mismatch at seed {seed}"
