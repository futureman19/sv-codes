"""Tests for svcode.anchor — BMP-0002 L2 on-chain anchoring (spec §3–§5)."""
from __future__ import annotations

import json
import pathlib

import pytest

from svcode import anchor, tx as txm
from svcode.crypto import key_from_hex
from svcode.envelope import Envelope

VECTORS = json.loads(
    (pathlib.Path(__file__).parent.parent / "vectors" / "vectors.json").read_text()
)
AUTH_PRIV = VECTORS["private_key_hex"]
AUTH_PUB = VECTORS["authority_pubkey_compressed"]

PAYER_PRIV = 2  # fee-payer key (separate from authority by design)
TARGET = 0x53564331


def signed_envelope(text: str = "HELLO, CHAIN.") -> bytes:
    env = Envelope(target_id=TARGET, action=0x00FF, payload=text.encode())
    env.sign(key_from_hex(AUTH_PRIV))
    return env.serialize()


def fake_utxos(n=1, value=10_000):
    return [{"txid": f"{0x11 + i:02x}" * 32, "vout": i, "value": value} for i in range(n)]


def build(text="HELLO, CHAIN.", **kw):
    env_bytes = signed_envelope(text)
    raw_hex, txid, prevouts = anchor.build_l2_tx(env_bytes, fake_utxos(), PAYER_PRIV, **kw)
    return raw_hex, txid, prevouts, env_bytes


# ---------- push encoding / data output shape ----------

def test_pushdata_boundaries():
    assert anchor.pushdata(b"a" * 75) == bytes([75]) + b"a" * 75
    assert anchor.pushdata(b"a" * 76)[:2] == b"\x4c\x4c"
    assert anchor.pushdata(b"a" * 255)[:2] == b"\x4c\xff"
    assert anchor.pushdata(b"a" * 256)[:3] == b"\x4d\x00\x01"


def test_data_script_layout():
    s = anchor.data_script(b"ENVDATA")
    assert s[0] == 0x00 and s[1] == 0x6A
    push, off = txm.read_push(s, 2)
    assert off == len(s) and push[:4] == anchor.MAGIC and push[4:] == b"ENVDATA"


# ---------- build / extract ----------

def test_build_parse_extract_roundtrip():
    raw_hex, txid, prevouts, env_bytes = build()
    parsed = txm.parse_tx(bytes.fromhex(raw_hex))
    assert parsed["txid"] == txid
    assert parsed["outputs"][0][0] == 0  # data output is zero-value
    assert anchor.extract_envelope(bytes.fromhex(raw_hex)) == env_bytes
    env = Envelope.parse(anchor.extract_envelope(bytes.fromhex(raw_hex)))
    assert env.action == 0x00FF and env.payload == b"HELLO, CHAIN."


def test_multi_input_tx():
    raw_hex, _txid, prevouts, _e = build()
    raw_hex2, _t2, prevouts2, _e2 = build()
    env_bytes = signed_envelope("MULTI")
    raw_hex3, _t3, prevouts3 = anchor.build_l2_tx(
        env_bytes, fake_utxos(2), PAYER_PRIV)
    assert len(txm.parse_tx(bytes.fromhex(raw_hex3))["inputs"]) == 2
    assert len(prevouts3) == 2


# ---------- verify: happy path + authority ----------

def test_verify_happy_path():
    raw_hex, txid, prevouts, _ = build()
    seen = {}
    env = anchor.verify_l2(bytes.fromhex(raw_hex), prevouts, AUTH_PUB, seen)
    assert env.target_id == TARGET and env.payload == b"HELLO, CHAIN."
    assert len(seen) == 1 and list(seen.values())[0] == txid


def test_verify_wrong_authority_rejected():
    raw_hex, _t, prevouts, _ = build()
    from svcode.crypto import generate_key, pubkey_hex
    wrong = pubkey_hex(generate_key())
    with pytest.raises(ValueError, match="envelope signature invalid"):
        anchor.verify_l2(bytes.fromhex(raw_hex), prevouts, wrong, {})


def test_verify_tampered_envelope_rejected():
    env_bytes = bytearray(signed_envelope())
    env_bytes[-1] ^= 0xFF  # flip a payload byte
    raw_hex, _t, prevouts = anchor.build_l2_tx(bytes(env_bytes), fake_utxos(), PAYER_PRIV)
    with pytest.raises(ValueError, match="envelope signature invalid"):
        anchor.verify_l2(bytes.fromhex(raw_hex), prevouts, AUTH_PUB, {})


# ---------- payment evidence checks ----------

def test_missing_evidence_rejected():
    raw_hex, _t, _p, _ = build()
    with pytest.raises(ValueError, match="missing prevout evidence"):
        anchor.verify_l2(bytes.fromhex(raw_hex), [], AUTH_PUB, {})


def test_forged_prevout_value_rejected():
    raw_hex, _t, prevouts, _ = build()
    forged = [dict(p, value=p["value"] * 100) for p in prevouts]
    with pytest.raises(ValueError, match="signature invalid"):
        anchor.verify_l2(bytes.fromhex(raw_hex), forged, AUTH_PUB, {})


def test_forged_prevout_script_rejected():
    raw_hex, _t, prevouts, _ = build()
    other_pub = txm.compress_pub(txm.pubkey_from_priv(99))
    forged = [dict(p, script_hex=txm.p2pkh_script(other_pub).hex()) for p in prevouts]
    with pytest.raises(ValueError, match="pubkey does not match prevout"):
        anchor.verify_l2(bytes.fromhex(raw_hex), forged, AUTH_PUB, {})


def test_no_fee_rejected():
    env_bytes = signed_envelope()
    raw_hex, _t, prevouts = anchor.build_l2_tx(env_bytes, fake_utxos(), PAYER_PRIV, fee=0)
    with pytest.raises(ValueError, match="no fee paid"):
        anchor.verify_l2(bytes.fromhex(raw_hex), prevouts, AUTH_PUB, {})


def test_wrong_sighash_type_rejected():
    raw_hex, _t, prevouts, _ = build()
    raw = bytearray(bytes.fromhex(raw_hex))
    parsed = txm.parse_tx(bytes(raw))
    # locate input 0 scriptSig in raw: 4 version + 1 count + 36 outpoint + 1 len
    off = 4 + 1 + 36
    sig_push_len = parsed["inputs"][0]["script_sig"][0]  # push op = total sig bytes (DER+hashtype)
    sighash_off = off + 1 + sig_push_len  # varint len + push op + DER → hashtype byte
    assert raw[sighash_off] == 0x41
    raw[sighash_off] = 0x01
    with pytest.raises(ValueError, match="wrong sighash type"):
        anchor.verify_l2(bytes(raw), prevouts, AUTH_PUB, {})


def test_double_bmp1_output_rejected():
    env_bytes = signed_envelope()
    raw_hex, _t, prevouts = anchor.build_l2_tx(env_bytes, fake_utxos(), PAYER_PRIV)
    parsed = txm.parse_tx(bytes.fromhex(raw_hex))
    # rebuild with a second BMP1 data output grafted on
    outputs = list(parsed["outputs"]) + [(0, anchor.data_script(b"x" * 85))]
    raw2 = ((1).to_bytes(4, "little")
            + txm.varint(len(parsed["inputs"]))
            + b"".join(i["outpoint"] + txm.varint(len(i["script_sig"])) + i["script_sig"] + i["sequence"]
                       for i in parsed["inputs"])
            + txm.varint(len(outputs))
            + b"".join(txm.ser_output(v, s) for v, s in outputs)
            + (0).to_bytes(4, "little"))
    with pytest.raises(ValueError, match="multiple BMP1"):
        anchor.verify_l2(raw2, prevouts, AUTH_PUB, {})


# ---------- freshness (anti-reuse) ----------

def test_double_spend_rejected_and_duplicate_ok():
    seen = {}
    raw1, txid1, p1, _ = build("COMMAND ONE")
    env1 = anchor.verify_l2(bytes.fromhex(raw1), p1, AUTH_PUB, seen)
    assert env1.payload == b"COMMAND ONE"
    # re-presenting the SAME txid is idempotent
    anchor.verify_l2(bytes.fromhex(raw1), p1, AUTH_PUB, seen)
    # a DIFFERENT tx spending the same outpoint is a double-spend
    raw2, txid2, p2, _ = build("COMMAND TWO")
    assert txid2 != txid1
    with pytest.raises(ValueError, match="double-spend"):
        anchor.verify_l2(bytes.fromhex(raw2), p2, AUTH_PUB, seen)


# ---------- end-to-end: build with on-chain-shaped utxo ----------

def test_faucet_style_utxo_endtoend():
    """Mimics the live demo: faucet-shaped UTXO pays for an authority-signed command."""
    env = Envelope(target_id=TARGET, action=0x00A1,
                   params=(37774900).to_bytes(4, "big", signed=True)
                   + (-122419400).to_bytes(4, "big", signed=True),
                   payload=b'{"note":"anchored move"}')
    env.sign(key_from_hex(AUTH_PRIV))
    utxos = [{"txid": "ab" * 32, "vout": 0, "value": 50_000}]
    raw_hex, txid, prevouts = anchor.build_l2_tx(env.serialize(), utxos, PAYER_PRIV, fee=300)
    out = anchor.verify_l2(bytes.fromhex(raw_hex), prevouts, AUTH_PUB, {})
    assert out.action_name == "MOVE_TO"
    parsed = txm.parse_tx(bytes.fromhex(raw_hex))
    assert sum(v for v, _ in parsed["outputs"]) == 50_000 - 300
