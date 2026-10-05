"""Stream framing (SV-0001 §3.1).

stream = uint32_BE Content_Length || uint32_BE CRC32(content) || content || zero-pad
Padding rounds the stream up to a multiple of 32 bytes (one 256-bit symbol).
"""

from __future__ import annotations

import struct

from .crypto import crc32

SYMBOL_BYTES = 32  # 256 bits


class StreamError(ValueError):
    pass


def build_stream(content: bytes) -> bytes:
    raw = 8 + len(content)
    padded = (raw + SYMBOL_BYTES - 1) // SYMBOL_BYTES * SYMBOL_BYTES
    out = bytearray(padded)
    struct.pack_into(">I", out, 0, len(content))
    struct.pack_into(">I", out, 4, crc32(content))
    out[8 : 8 + len(content)] = content
    return bytes(out)


def split_symbols(stream: bytes) -> list[bytes]:
    if len(stream) % SYMBOL_BYTES != 0:
        raise StreamError("stream length must be a multiple of 32 bytes")
    return [stream[i : i + SYMBOL_BYTES] for i in range(0, len(stream), SYMBOL_BYTES)]


def parse_stream(buf: bytes) -> bytes:
    """Validate length + CRC32, return content. Raises StreamError on corruption."""
    if len(buf) < 8 or len(buf) % SYMBOL_BYTES != 0:
        raise StreamError("malformed stream buffer")
    clen, crc = struct.unpack(">II", buf[:8])
    if 8 + clen > len(buf):
        raise StreamError(f"declared length {clen} exceeds buffer")
    content = bytes(buf[8 : 8 + clen])
    if crc32(content) != crc:
        raise StreamError("CRC32 mismatch")
    return content
