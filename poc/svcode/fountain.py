"""Luby Transform fountain coding (SV-0001 §3.2).

Deterministic symbol stream:
    R(s, i) = SHA-256( "SV1" || uint16_BE s || uint8 i || uint32_BE j )
              concatenated over block counter j = 0, 1, 2, ...
    consumed sequentially as big-endian uint32 draws.

Degree: Robust Soliton (c=0.1, delta=0.5), inverse-CDF on the first draw
(u = draw / 2^32). Indices: repeated draws mod K, re-draw on collision.

This module is bit-exact with the SV-0001 JS transmitter on the website;
the parity is pinned by golden test vectors (poc/vectors/).
"""

from __future__ import annotations

import math
from collections.abc import Iterator

from .crypto import sha256

ROBUST_C = 0.1
ROBUST_DELTA = 0.5
TWO32 = 4294967296


def rand_draws(seed: int, slot: int) -> Iterator[int]:
    """Infinite stream of uint32 draws for (seed, slot)."""
    base = b"SV1" + (seed & 0xFFFF).to_bytes(2, "big") + bytes([slot & 0xFF])
    j = 0
    while True:
        block = sha256(base + j.to_bytes(4, "big"))
        for off in range(0, 32, 4):
            yield int.from_bytes(block[off : off + 4], "big")
        j += 1


def soliton_cdf(k: int) -> list[float]:
    """Robust Soliton CDF over degrees 1..k. cdf[0] is unused (0.0)."""
    r = ROBUST_C * math.log(k / ROBUST_DELTA) * math.sqrt(k)
    tau = [0.0] * (k + 1)
    cut = max(1, math.floor(k / r))
    # mirror the reference JS exactly: tau entries beyond k are computed there
    # (JS arrays auto-extend) but never consumed by the degree loop.
    for d in range(1, min(cut, k + 1)):
        tau[d] = r / (d * k)
    if cut <= k:
        tau[cut] += r * math.log(r / ROBUST_DELTA) / k

    def rho(d: int) -> float:
        return 1.0 / k if d == 1 else 1.0 / (d * (d - 1))

    z = 0.0
    mu = [0.0] * (k + 1)
    for d in range(1, k + 1):
        mu[d] = rho(d) + tau[d]
        z += mu[d]
    cdf = [0.0] * (k + 1)
    acc = 0.0
    for d in range(1, k + 1):
        acc += mu[d] / z
        cdf[d] = acc
    return cdf


def sample_degree(cdf: list[float], u: float) -> int:
    for d in range(1, len(cdf)):
        if u <= cdf[d]:
            return d
    return len(cdf) - 1


def pick_indices(k: int, cdf: list[float], seed: int, slot: int) -> set[int]:
    """The exact source-symbol index set an encoder uses for (seed, slot)."""
    g = rand_draws(seed, slot)
    d = min(sample_degree(cdf, next(g) / TWO32), k)
    picked: set[int] = set()
    while len(picked) < d:
        picked.add(next(g) % k)
    return picked


def xor_symbols(symbols: list[bytes], indices: set[int]) -> bytes:
    out = bytearray(32)
    for idx in indices:
        src = symbols[idx]
        for b in range(32):
            out[b] ^= src[b]
    return bytes(out)


def encode_symbol(symbols: list[bytes], cdf: list[float], seed: int, slot: int) -> bytes:
    """Encoded 256-bit symbol for (seed, slot). seed=0 → static identity mode."""
    k = len(symbols)
    if seed == 0:
        return symbols[slot] if slot < k else bytes(32)
    return xor_symbols(symbols, pick_indices(k, cdf, seed, slot))


class LTDecoder:
    """Incremental LT decoder over GF(2) for 256-bit symbols.

    Feed (seed, slot, data) tuples from decoded frames in any order;
    solved() returns the K source symbols once rank K is reached.
    """

    def __init__(self, k: int):
        self.k = k
        self.cdf = soliton_cdf(k)
        self._rows: list[list] = []  # [mask:int, data:bytearray]
        self._seen: set[tuple[int, int]] = set()

    def add_frame_symbol(self, seed: int, slot: int, data: bytes) -> bool:
        """Add one encoded symbol. Returns True if decoding completed now."""
        if len(data) != 32:
            raise ValueError("symbol must be 32 bytes")
        if seed == 0:  # static identity mode
            picked = {slot} if slot < self.k else set()
            if slot >= self.k:
                return self.solved() is not None
        else:
            if (seed, slot) in self._seen:
                return self.solved() is not None
            picked = pick_indices(self.k, self.cdf, seed, slot)
        self._seen.add((seed, slot))

        mask = 0
        for idx in picked:
            mask |= 1 << idx
        row = [mask, bytearray(data)]
        # reduce against existing pivots
        for pr in self._rows:
            pivot_bit = 1 << pr[2]
            if row[0] & pivot_bit:
                row[0] ^= pr[0]
                for b in range(32):
                    row[1][b] ^= pr[1][b]
        if row[0] == 0:
            return self.solved() is not None
        pivot = (row[0] & -row[0]).bit_length() - 1
        # eliminate this pivot from existing rows (keeps rows fully reduced)
        for pr in self._rows:
            if pr[0] & (1 << pivot):
                pr[0] ^= row[0]
                for b in range(32):
                    pr[1][b] ^= row[1][b]
        row.append(pivot)
        self._rows.append(row)
        return len(self._rows) == self.k

    def symbol_count(self) -> int:
        return len(self._rows)

    def solved(self) -> list[bytes] | None:
        if len(self._rows) != self.k:
            return None
        out: list[bytes | None] = [None] * self.k
        for mask, data, pivot in self._rows:
            if mask != (1 << pivot):  # fully reduced rows must be pure
                return None
            out[pivot] = bytes(data)
        if any(s is None for s in out):
            return None
        return out  # type: ignore[return-value]
