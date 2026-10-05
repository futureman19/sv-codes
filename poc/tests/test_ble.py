"""test_ble.py — BMP-0001 (BMP-BLE) codec tests."""
from __future__ import annotations

import random

from svcode import ble
from svcode.crypto import key_from_hex, pubkey_hex, vk_from_hex
from svcode.envelope import Envelope
from svcode.stream import build_stream, parse_stream

GOLDEN_PRIV = "1fbf0a5d03e1b7db0ef88a9d107d143e8bc2710e4e9ae656956e0f948037f1ba"


def signed_envelope(msg: bytes) -> Envelope:
    env = Envelope(target_id=0x53564331, action=0x00FF, payload=msg)
    env.sign(key_from_hex(GOLDEN_PRIV))
    return env


def test_legacy_roundtrip():
    stream = build_stream(signed_envelope(b"HALT on channel 7").serialize())
    frags = ble.fragment(stream, stream_seq=3)
    r = ble.Reassembler()
    got = None
    for f in frags:
        got = r.feed(f) or got
    assert got == stream
    assert len(frags[0]) == 24  # 19-byte MTU + 5-byte header


def test_loss_shuffle_cycles():
    stream = build_stream(signed_envelope(b"HALT on channel 7").serialize())
    frags = ble.fragment(stream, stream_seq=3)
    rng = random.Random(42)
    r = ble.Reassembler()
    got = None
    for _ in range(6):
        order = frags[:]
        rng.shuffle(order)
        for f in order:
            if rng.random() < 0.4:
                continue  # lost this cycle
            got = r.feed(f) or got
        if got:
            break
    assert got == stream


def test_generation_change():
    old = ble.fragment(build_stream(signed_envelope(b"HALT").serialize()), stream_seq=3)
    new_stream = build_stream(signed_envelope(b"RESUME").serialize())
    r = ble.Reassembler()
    r.feed(old[0]); r.feed(old[1])  # partial old generation
    got = None
    for f in ble.fragment(new_stream, stream_seq=4):
        got = r.feed(f) or got
    assert got == new_stream


def test_malformed_pdus():
    frags = ble.fragment(build_stream(signed_envelope(b"HALT").serialize()), stream_seq=3)
    r = ble.Reassembler()
    assert r.feed(b"") is None
    assert r.feed(b"XX" + frags[0][2:]) is None            # bad magic
    bad = bytearray(frags[0]); bad[4] = 0
    assert r.feed(bytes(bad)) is None                       # Frag_Count = 0
    bad2 = bytearray(frags[0]); bad2[3] = 9
    assert r.feed(bytes(bad2)) is None                      # Frag_Index out of range
    r.feed(frags[0])
    bad3 = bytearray(frags[1]); bad3[4] = frags[0][4] + 1
    assert r.feed(bytes(bad3)) is None                      # inconsistent count in generation


def test_extended_single_pdu():
    stream = build_stream(signed_envelope(b"GO").serialize())
    ex = ble.fragment(stream, stream_seq=1, mtu=ble.EXTENDED_MTU)
    assert len(ex) == 1
    assert ble.Reassembler().feed(ex[0]) == stream


def test_end_to_end_signature():
    msg = b"MOVE_TO dock alpha, then report status over BMP-BLE transport!!"
    stream = build_stream(signed_envelope(msg).serialize())
    frags = ble.fragment(stream, stream_seq=9)
    rng = random.Random(7)
    r = ble.Reassembler()
    got = None
    for _ in range(8):
        order = frags[:]
        rng.shuffle(order)
        for f in order:
            if rng.random() < 0.35:
                continue
            got = r.feed(f) or got
        if got:
            break
    assert got is not None
    env = Envelope.parse(parse_stream(got))
    assert env.verify(vk_from_hex(pubkey_hex(key_from_hex(GOLDEN_PRIV))))
    assert env.payload == msg


def test_on_air_layout():
    frags = ble.fragment(build_stream(signed_envelope(b"HALT").serialize()), stream_seq=3)
    pdu = ble.pack_pdu(frags[0])
    assert len(pdu) == 31
    assert pdu[0] == 0x02 and pdu[1] == 0x01 and pdu[2] == 0x06   # flags
    assert pdu[3] == 0x1B and pdu[4] == 0xFF                     # MSD header
    assert pdu[5] == 0xFF and pdu[6] == 0xFF                     # company 0xFFFF LE
    assert pdu[7:9] == b"SV"                                     # magic
    assert ble.unpack_pdu(pdu) == frags[0]
    assert ble.unpack_pdu(bytes(31)) is None


def test_poisoned_generation_drops_all():
    """spec §5.3: an inconsistent fragment poisons the WHOLE generation."""
    stream = build_stream(signed_envelope(b"HALT on channel 7").serialize())
    frags = ble.fragment(stream, stream_seq=3)
    assert len(frags) >= 4
    r = ble.Reassembler()
    for f in frags[:3]:
        r.feed(f)
    bad = bytearray(frags[3]); bad[4] = frags[3][4] + 1  # count mismatch
    assert r.feed(bytes(bad)) is None
    # if the old buffer had survived, feeding the tail would complete here:
    got = None
    for f in frags[3:]:
        got = r.feed(f) or got
    assert got is None, "poisoned generation was not fully discarded"
    # self-heal: the next full cycle completes cleanly and correctly
    got = None
    for f in frags:
        got = r.feed(f) or got
    assert got == stream


def test_poisoned_generation_mtu_mismatch():
    stream = build_stream(signed_envelope(b"HALT on channel 7").serialize())
    frags = ble.fragment(stream, stream_seq=3)
    r = ble.Reassembler()
    r.feed(frags[0]); r.feed(frags[1])
    short = frags[2][:-3]  # same seq/count, shorter data → implied-grid mismatch
    assert r.feed(short) is None
    got = None
    for f in frags[2:]:
        got = r.feed(f) or got
    assert got is None, "poisoned generation was not fully discarded"
    got = None
    for f in frags:
        got = r.feed(f) or got
    assert got == stream


def test_duplicate_fragments_harmless():
    stream = build_stream(signed_envelope(b"HALT on channel 7").serialize())
    frags = ble.fragment(stream, stream_seq=3)
    r = ble.Reassembler()
    got = None
    for f in [frags[0], frags[0], frags[1], frags[1], frags[2], frags[0]] + frags:
        got = r.feed(f) or got
    assert got == stream
