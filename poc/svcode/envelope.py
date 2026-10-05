"""BMP envelope (BMP-0000 §4). 85-byte fixed header + variable payload.

Layout (all integers big-endian):
    0x00  1   Version (0x01)
    0x01  4   Target_ID
    0x05  2   Action_Code
    0x07  8   Params
    0x0F  4   Nonce (unix seconds, timestamp mode)
    0x13  2   Payload_Length
    0x15  64  Signature (ECDSA/secp256k1 compact r||s)
    0x55  ..  Payload_Data
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field

from .crypto import sha256, sign_digest, verify_digest

VERSION = 0x01
HEADER_LEN = 85

# Core action codes (BMP-0000 §6)
ACTION_NAMES = {
    0x0000: "NOP",
    0x0001: "HALT",
    0x0002: "REPORT_STATUS",
    0x00A1: "MOVE_TO",
    0x00A2: "MOVE_VECTOR",
    0x00B1: "CLAIM_BOUNTY",
    0x00C1: "SET_CONFIG",
    0x00FF: "VENDOR",
}


class EnvelopeError(ValueError):
    pass


@dataclass
class Envelope:
    target_id: int
    action: int
    params: bytes = b"\x00" * 8
    nonce: int = 0
    payload: bytes = b""
    signature: bytes = b"\x00" * 64
    version: int = VERSION

    def __post_init__(self):
        if len(self.params) != 8:
            raise EnvelopeError("params must be exactly 8 bytes")
        if len(self.signature) != 64:
            raise EnvelopeError("signature must be exactly 64 bytes")
        if not (0 <= self.target_id <= 0xFFFFFFFF):
            raise EnvelopeError("target_id must be uint32")
        if not (0 <= self.action <= 0xFFFF):
            raise EnvelopeError("action must be uint16")
        if len(self.payload) > 0xFFFF:
            raise EnvelopeError("payload too large for uint16 length")
        if self.nonce == 0:
            self.nonce = int(time.time())

    def header21(self) -> bytes:
        """The 21 signed header bytes (0x00..0x14)."""
        return (
            struct.pack(">B", self.version)
            + struct.pack(">I", self.target_id)
            + struct.pack(">H", self.action)
            + self.params
            + struct.pack(">I", self.nonce)
            + struct.pack(">H", len(self.payload))
        )

    def digest(self) -> bytes:
        return sha256(self.header21() + self.payload)

    def serialize(self) -> bytes:
        return self.header21() + self.signature + self.payload

    def sign(self, sk) -> None:
        self.signature = sign_digest(sk, self.digest())

    def verify(self, vk) -> bool:
        return verify_digest(vk, self.signature, self.digest())

    @property
    def action_name(self) -> str:
        return ACTION_NAMES.get(self.action, f"0x{self.action:04X}")

    @classmethod
    def parse(cls, data: bytes) -> "Envelope":
        if len(data) < HEADER_LEN:
            raise EnvelopeError(f"envelope too short: {len(data)} < {HEADER_LEN}")
        version = data[0]
        if version != VERSION:
            raise EnvelopeError(f"unsupported envelope version 0x{version:02x}")
        target_id = struct.unpack(">I", data[1:5])[0]
        action = struct.unpack(">H", data[5:7])[0]
        params = data[7:15]
        nonce = struct.unpack(">I", data[15:19])[0]
        plen = struct.unpack(">H", data[19:21])[0]
        if len(data) != HEADER_LEN + plen:
            raise EnvelopeError(
                f"length mismatch: got {len(data)} bytes, header declares {HEADER_LEN + plen}"
            )
        return cls(
            target_id=target_id,
            action=action,
            params=params,
            nonce=nonce,
            payload=data[HEADER_LEN:],
            signature=data[21:85],
            version=version,
        )


def demo_envelope(text: str, target_id: int = 0x53564331, action: int = 0x00FF) -> Envelope:
    """Convenience: vendor-action envelope carrying UTF-8 text."""
    return Envelope(target_id=target_id, action=action, payload=text.encode("utf-8"))
