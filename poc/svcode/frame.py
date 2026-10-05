"""SV-0001 frame packing (§2/§3): the 2,704-bit payload matrix.

Bit layout (row-major over the 52x52 payload matrix):
    bits 0-15      Seed (uint16 BE)
    bits 16-23     Content_Type (uint8)
    bits 24-39     K (uint16 BE, source-symbol count)
    bits 40-2599   ten 256-bit encoded symbols (slots 0..9)
    bits 2600-2703 reserved (zero)

The payload matrix sits at rows 6..57, cols 6..57 of the 64x64 grid;
bit i -> cell (6 + i//52, 6 + i%52).
"""

from __future__ import annotations

FRAME_BITS = 2704
GRID = 64
INNER = 52
OFFSET = 6  # payload origin row/col

CONTENT_ENVELOPE = 0x01
CONTENT_RAW_TX = 0x02
CONTENT_BEEF = 0x03


class FrameError(ValueError):
    pass


def pack_frame(symbols10: list[bytes], seed: int, ctype: int, k: int) -> list[int]:
    """Pack header + ten 32-byte symbols into the 2,704-bit payload matrix."""
    if len(symbols10) != 10:
        raise FrameError("frame carries exactly 10 symbols")
    if not (0 <= seed <= 0xFFFF):
        raise FrameError("seed must be uint16")
    if not (1 <= k <= 0xFFFF):
        raise FrameError("k must be 1..65535")
    bits = [0] * FRAME_BITS
    n = 0

    def put(value: int, count: int) -> None:
        nonlocal n
        for b in range(count - 1, -1, -1):
            bits[n] = (value >> b) & 1
            n += 1

    put(seed, 16)
    put(ctype, 8)
    put(k, 16)
    for sym in symbols10:
        if len(sym) != 32:
            raise FrameError("symbol must be 32 bytes")
        for byte in sym:
            put(byte, 8)
    return bits


def unpack_frame(bits: list[int] | bytes) -> tuple[int, int, int, list[bytes]]:
    """Inverse of pack_frame: returns (seed, content_type, k, ten symbols)."""
    if len(bits) != FRAME_BITS:
        raise FrameError(f"expected {FRAME_BITS} bits, got {len(bits)}")

    def read(off: int, n: int) -> int:
        v = 0
        for i in range(n):
            v = (v << 1) | int(bits[off + i])
        return v

    seed = read(0, 16)
    ctype = read(16, 8)
    k = read(24, 16)
    symbols = []
    for slot in range(10):
        base = 40 + slot * 256
        sym = bytes(read(base + b * 8, 8) for b in range(32))
        symbols.append(sym)
    return seed, ctype, k, symbols


def frame_bit_to_cell(i: int) -> tuple[int, int]:
    """Payload-matrix bit index -> grid (row, col)."""
    return OFFSET + i // INNER, OFFSET + i % INNER
