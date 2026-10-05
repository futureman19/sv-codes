"""High-level SV Code codec: content <-> frame sequence.

Encoder:  content -> stream -> frames (seed 0 static if K<=10, else seeds 1,2,3...)
Decoder:  frames (from decode_image) -> content. K is read from the frame
          header (SV-0001 §3), so degree/index reconstruction is deterministic.
"""

from __future__ import annotations

from .fountain import LTDecoder, encode_symbol, soliton_cdf
from .frame import pack_frame, unpack_frame
from .stream import build_stream, parse_stream, split_symbols

STATIC_MAX_K = 10  # frames carry 10 symbols; K<=10 fits one static frame


class Encoder:
    def __init__(self, content: bytes, ctype: int = 0x01):
        self.content = content
        self.ctype = ctype
        self.stream = build_stream(content)
        self.symbols = split_symbols(self.stream)
        self.k = len(self.symbols)
        self.cdf = soliton_cdf(self.k)
        self.static = self.k <= STATIC_MAX_K

    def frame_bits(self, seq: int) -> tuple[int, list[int]]:
        """Return (seed, bits) for the seq-th frame of the broadcast loop."""
        seed = 0 if self.static else (seq % 65535) + 1
        encoded = [encode_symbol(self.symbols, self.cdf, seed, slot) for slot in range(10)]
        return seed, pack_frame(encoded, seed, self.ctype, self.k)


class Decoder:
    """Collects decoded frames until the fountain code solves the stream.

    State is keyed by K (declared in every frame header). On full rank with a
    failed CRC (interleaved streams), the K-state resets and collection
    continues — the transmitter's loop guarantees one stream dominates.
    """

    def __init__(self):
        self._lts: dict[int, LTDecoder] = {}
        self._seen: set[tuple[int, int, int]] = set()  # (k, seed, slot)
        self.frames_seen = 0
        self.last_k: int | None = None

    def feed_bits(self, bits: list[int]) -> bytes | None:
        """Feed one decoded frame; returns content bytes when solved+CRC-ok."""
        seed, _ctype, k, symbols = unpack_frame(bits)
        self.frames_seen += 1
        self.last_k = k
        lt = self._lts.setdefault(k, LTDecoder(k))
        for slot, sym in enumerate(symbols):
            if sym == bytes(32):
                continue
            key = (k, seed, slot)
            if key in self._seen:
                continue
            self._seen.add(key)
            if lt.add_frame_symbol(seed, slot, sym):
                solved = lt.solved()
                if solved is None:
                    continue
                buf = b"".join(solved)
                try:
                    return parse_stream(buf)
                except Exception:
                    # wrong/corrupted mixture: reset this K and keep going
                    del self._lts[k]
                    self._seen = {s for s in self._seen if s[0] != k}
                    return None
        return None

    def progress(self) -> tuple[int, int] | None:
        """(symbols_collected, K) for the active stream, if known."""
        if self.last_k is None or self.last_k not in self._lts:
            return None
        lt = self._lts[self.last_k]
        return lt.symbol_count(), self.last_k
