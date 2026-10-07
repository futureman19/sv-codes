"""SV-0005 QR-inlay matrix (Draft): 96x96 grid with a center QR inlay.

The inlay edition carries a standard SV frame (header + fountain slots) in
every inner-matrix cell EXCEPT a reserved center block that holds a scannable
QR code. Any phone camera reads the QR (the onboarding bridge); the SV
scanner reads the signed payload around it.

Geometry (canonical layout):
    96x96 grid, 6-cell border, 84x84 inner matrix (7,056 cells).
    Inlay = QR (modules + quiet-zone border) rendered at QR_SCALE cells per
    module, centered in the inner matrix. All remaining cells are payload.

Frame layout: identical to SV-0001 section 3 (seed16 | ctype8 | k16 header,
then N 256-bit slots), but mapped row-major over the usable (non-inlay)
cells and zero-padded. N = floor((usable - 40) / 256).

Encoding rule (normative): inlay frames broadcast in fountain mode with
seed >= 1 even when K <= N, so every slot carries real encoded data. This
keeps the matrix uniformly dense and makes the frame decodable from any
sufficient subset of its slots (erasure robustness against print damage).
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from .decode import find_anchors  # hue-mask anchor finder is grid-agnostic
from .fountain import LTDecoder, encode_symbol, soliton_cdf
from .stream import build_stream, parse_stream, split_symbols

GRID = 96
OFFSET = 6
INNER = 84
WARP_SCALE = 10

ANCHOR_PURE = {
    "tl": (0, 255, 255),
    "tr": (255, 0, 255),
    "bl": (255, 255, 0),
    "br": (255, 0, 0),
}
ANCHOR_CELLS = {"tl": (0, 0), "tr": (0, 92), "bl": (92, 0), "br": (92, 92)}

HEADER_BITS = 40
SYMBOL_BITS = 256

CONTENT_ENVELOPE = 0x01


class InlayError(ValueError):
    pass


@dataclass(frozen=True)
class InlayLayout:
    """Resolved inlay geometry for one QR payload."""

    qr_payload: str
    qr_border: int
    qr_scale: int
    qmat: tuple  # tuple of tuple of bool, includes quiet-zone border
    qcells: int  # QR side in cells (modules + border), pre-scaling
    inlay: int  # reserved center side in inner-matrix cells
    inlay0: int  # first inner row/col of the inlay
    nslots: int  # fountain slots that fit around the inlay

    def in_inlay(self, r: int, c: int) -> bool:
        return self.inlay0 <= r < self.inlay0 + self.inlay and self.inlay0 <= c < self.inlay0 + self.inlay

    @property
    def usable_cells(self) -> list[tuple[int, int]]:
        return [(r, c) for r in range(INNER) for c in range(INNER) if not self.in_inlay(r, c)]

    @property
    def frame_bits(self) -> int:
        return HEADER_BITS + self.nslots * SYMBOL_BITS


def layout_for(qr_payload: str, qr_border: int = 2, qr_scale: int = 1,
               ec=None) -> InlayLayout:
    """Resolve the canonical inlay layout for a QR payload string."""
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H

    qr = qrcode.QRCode(error_correction=ec if ec is not None else ERROR_CORRECT_H,
                       border=qr_border)
    qr.add_data(qr_payload)
    qr.make(fit=True)
    qmat = tuple(tuple(bool(v) for v in row) for row in qr.get_matrix())
    qcells = len(qmat)
    inlay = qcells * qr_scale
    if inlay >= INNER - 8:
        raise InlayError(f"QR too large for the matrix: inlay {inlay} cells")
    inlay0 = (INNER - inlay) // 2
    usable = INNER * INNER - inlay * inlay
    nslots = (usable - HEADER_BITS) // SYMBOL_BITS
    if nslots < 1:
        raise InlayError("inlay leaves no room for payload slots")
    return InlayLayout(qr_payload, qr_border, qr_scale, qmat, qcells,
                       inlay, inlay0, nslots)


# ---------- frame packing ----------

def pack_inlay(symbols: list[bytes], seed: int, ctype: int, k: int,
               layout: InlayLayout) -> list[int]:
    """Pack header + slots into the usable cells (zero-padded)."""
    if len(symbols) > layout.nslots:
        raise InlayError(f"frame carries at most {layout.nslots} symbols")
    bits: list[int] = []

    def put(value: int, count: int) -> None:
        for b in range(count - 1, -1, -1):
            bits.append((value >> b) & 1)

    put(seed, 16)
    put(ctype, 8)
    put(k, 16)
    for sym in symbols:
        if len(sym) != 32:
            raise InlayError("symbol must be 32 bytes")
        for byte in sym:
            put(byte, 8)
    bits += [0] * (len(layout.usable_cells) - len(bits))
    return bits


def unpack_inlay(bits: list[int], layout: InlayLayout) -> tuple[int, int, int, list[bytes]]:
    if len(bits) < layout.frame_bits:
        raise InlayError(f"expected at least {layout.frame_bits} bits, got {len(bits)}")

    def read(off: int, n: int) -> int:
        v = 0
        for i in range(n):
            v = (v << 1) | int(bits[off + i])
        return v

    seed, ctype, k = read(0, 16), read(16, 8), read(24, 16)
    symbols = [bytes(read(HEADER_BITS + s * SYMBOL_BITS + b * 8, 8) for b in range(32))
               for s in range(layout.nslots)]
    return seed, ctype, k, symbols


# ---------- encoding ----------

def encode_inlay_frame(content: bytes, layout: InlayLayout, seed: int = 1,
                       ctype: int = CONTENT_ENVELOPE) -> list[int]:
    """Content -> one dense inlay frame (fountain mode, seed >= 1 required)."""
    if seed < 1:
        raise InlayError("inlay frames must broadcast with seed >= 1 (SV-0005 section 5)")
    symbols = split_symbols(build_stream(content))
    k = len(symbols)
    if k > layout.nslots:
        raise InlayError(f"content needs K={k} symbols, frame holds {layout.nslots}")
    cdf = soliton_cdf(k)
    encoded = [encode_symbol(symbols, cdf, seed, slot) for slot in range(layout.nslots)]
    return pack_inlay(encoded, seed, ctype, k, layout)


# ---------- rendering ----------

def render_inlay(bits: list[int], layout: InlayLayout, scale: int = 10) -> Image.Image:
    size = GRID * scale
    img = Image.new("RGB", (size, size), (255, 255, 255))
    px = img.load()

    def fill(gr: int, gc: int, rgb: tuple[int, int, int]) -> None:
        for dy in range(scale):
            for dx in range(scale):
                px[gc * scale + dx, gr * scale + dy] = rgb

    for name, (r0, c0) in ANCHOR_CELLS.items():
        color = ANCHOR_PURE[name]
        for r in range(r0, r0 + 4):
            for c in range(c0, c0 + 4):
                fill(r, c, color)

    for bit, (r, c) in zip(bits, layout.usable_cells):
        if bit:
            fill(OFFSET + r, OFFSET + c, (0, 0, 0))

    for rr in range(layout.qcells):
        for cc in range(layout.qcells):
            if layout.qmat[rr][cc]:
                for dr in range(layout.qr_scale):
                    for dc in range(layout.qr_scale):
                        fill(OFFSET + layout.inlay0 + rr * layout.qr_scale + dr,
                             OFFSET + layout.inlay0 + cc * layout.qr_scale + dc,
                             (0, 0, 0))
    return img


# ---------- decoding ----------

def _canonical_centers() -> dict[str, tuple[float, float]]:
    a = 2.0 * WARP_SCALE
    b = (GRID - 2.0) * WARP_SCALE
    return {"tl": (a, a), "tr": (b, a), "bl": (a, b), "br": (b, b)}


def decode_inlay_image(bgr: np.ndarray, layout: InlayLayout) -> list[int]:
    """Camera image -> inlay frame bits. Raises InlayError."""
    try:
        anchors = find_anchors(bgr)
    except Exception as e:
        raise InlayError(str(e)) from e
    src = np.array([anchors[k] for k in ("tl", "tr", "bl", "br")], dtype=np.float32)
    dst = np.array([_canonical_centers()[k] for k in ("tl", "tr", "bl", "br")], dtype=np.float32)
    h, _ = cv2.findHomography(src, dst)
    size = GRID * WARP_SCALE
    warped = cv2.warpPerspective(bgr, h, (size, size))
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    # Threshold = midpoint of the per-cell mean extremes (SV-0001 scanner
    # contract). Otsu is WRONG here: on near-perfect bimodal fields its
    # theta collapses onto the black rail and every dark cell reads 0.
    cells = layout.usable_cells
    means = np.zeros(len(cells), dtype=np.float32)
    margin = WARP_SCALE // 4
    span = WARP_SCALE - 2 * margin
    for i, (r, c) in enumerate(cells):
        y0 = (OFFSET + r) * WARP_SCALE + margin
        x0 = (OFFSET + c) * WARP_SCALE + margin
        means[i] = float(gray[y0:y0 + span, x0:x0 + span].mean())
    theta = (float(means.min()) + float(means.max())) / 2.0

    n = layout.frame_bits
    return [1 if means[i] < theta else 0 for i in range(n)]


class InlayDecoder:
    """Collects inlay frames until the fountain solves (mirrors codec.Decoder)."""

    def __init__(self):
        self._lts: dict[int, LTDecoder] = {}
        self._seen: set[tuple[int, int, int]] = set()
        self.last_k: int | None = None

    def feed_bits(self, bits: list[int], layout: InlayLayout) -> bytes | None:
        seed, _ctype, k, symbols = unpack_inlay(bits, layout)
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
                try:
                    return parse_stream(b"".join(solved))
                except Exception:
                    del self._lts[k]
                    self._seen = {s for s in self._seen if s[0] != k}
                    return None
        return None
