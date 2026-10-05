"""Tests for svcode.spv — BMP-0003 L3, replaying the live mainnet proof vector
(poc/vectors/l3_live.json) offline."""
from __future__ import annotations

import json
import pathlib

import pytest

from svcode import spv
from svcode.crypto import generate_key, pubkey_hex

L3 = json.loads(
    (pathlib.Path(__file__).parent.parent / "vectors" / "l3_live.json").read_text()
)
BEEF = bytes.fromhex(L3["beef_hex"])
HEADERS = [bytes.fromhex(L3["subject_block"]["header_hex"]),
           bytes.fromhex(L3["parent_block"]["header_hex"])]
AUTH = L3["authority_pubkey"]
TIP = L3["tip_height_at_fetch"]


def test_live_vector_passes():
    env = spv.verify_l3(BEEF, AUTH, HEADERS, seen={}, tip_height=TIP, min_depth=1)
    assert env.payload.decode() == L3["expected_payload"]


def test_bump_parser_structure():
    doc = spv.parse_beef(BEEF)
    assert len(doc["bumps"]) == 2 and len(doc["txs"]) == 2
    assert doc["txs"][-1]["txid"] == L3["subject_txid"]   # subject is last (BRC-62 ordering)
    assert doc["txs"][0]["txid"] == L3["parent_txid"]
    for b in doc["bumps"]:
        assert b["block_height"] in (L3["subject_block"]["height"], L3["parent_block"]["height"])


def test_header_pow_real_blocks():
    for h in HEADERS:
        info = spv.verify_header(h)  # raises on PoW failure
        assert len(info["hash"]) == 64


def test_corrupt_bump_rejected():
    beef = bytearray(BEEF)
    beef[60] ^= 0xFF  # inside first BUMP's data
    with pytest.raises(ValueError):
        spv.verify_l3(bytes(beef), AUTH, HEADERS, seen={}, tip_height=TIP)


def test_corrupt_header_rejected():
    bad = bytearray(HEADERS[0]); bad[10] ^= 0xFF
    with pytest.raises(ValueError, match="proof-of-work"):
        spv.verify_l3(BEEF, AUTH, [bytes(bad), HEADERS[1]], seen={}, tip_height=TIP)


def test_missing_header_rejected():
    # only the parent header provided; subject's root lookup must fail
    only_parent = [h for h in HEADERS
                   if spv.verify_header(h)["merkle_root"] !=
                   spv.bump_root(spv.parse_beef(BEEF)["bumps"][1], L3["subject_txid"])]
    with pytest.raises(ValueError, match="merkle root not in header store"):
        spv.verify_l3(BEEF, AUTH, only_parent, seen={}, tip_height=TIP)


def test_wrong_authority_rejected():
    with pytest.raises(ValueError, match="envelope signature invalid"):
        spv.verify_l3(BEEF, pubkey_hex(generate_key()), HEADERS, seen={}, tip_height=TIP)


def test_depth_requirement_enforced():
    with pytest.raises(ValueError, match="insufficient burial depth"):
        spv.verify_l3(BEEF, AUTH, HEADERS, seen={},
                      tip_height=TIP, min_depth=TIP + 10)


def test_freshness_applies_at_l3():
    seen = {}
    spv.verify_l3(BEEF, AUTH, HEADERS, seen=seen, tip_height=TIP)
    # a different command reusing the same parent outpoint must be rejected
    # (the live vector's subject already consumed it)
    from svcode import anchor
    from svcode.crypto import key_from_hex
    from svcode.envelope import Envelope
    from pathlib import Path
    import json as _json
    V = _json.loads(Path(__file__).parent.parent.joinpath("vectors/vectors.json").read_text())
    l2 = _json.loads(Path(__file__).parent.parent.joinpath("vectors/l2_live.json").read_text())
    env2 = Envelope(target_id=0x53564331, action=0x00FF, payload=b"SECOND COMMAND")
    env2.sign(key_from_hex(V["private_key_hex"]))
    raw2, _t2, prev2 = anchor.build_l2_tx(
        env2.serialize(), [{"txid": l2["claim_txid"], "vout": 0, "value": 50_000}],
        int(l2["payer_priv_hex"], 16))
    with pytest.raises(ValueError, match="double-spend"):
        anchor.verify_l2(bytes.fromhex(raw2), prev2, AUTH, seen)
