"""Frame rendering (SV-0001 §2): bits -> image with chromatic anchors.

Anchor colors are the PURE hues (center of the §2.1 HSV ranges):
    TL cyan #00FFFF, TR magenta #FF00FF, BL yellow #FFFF00, BR red #FF0000.
"""

from __future__ import annotations

from PIL import Image

from .frame import FRAME_BITS, GRID, OFFSET, frame_bit_to_cell

ANCHOR_PURE = {
    "tl": (0, 255, 255),
    "tr": (255, 0, 255),
    "bl": (255, 255, 0),
    "br": (255, 0, 0),
}
ANCHOR_CELLS = {"tl": (0, 0), "tr": (0, 60), "bl": (60, 0), "br": (60, 60)}


def render_frame(bits: list[int], scale: int = 10) -> Image.Image:
    """Render 2,704 payload bits as a 64x64 grid image (scale px per cell)."""
    if len(bits) != FRAME_BITS:
        raise ValueError(f"expected {FRAME_BITS} bits")
    size = GRID * scale
    img = Image.new("RGB", (size, size), (255, 255, 255))  # quiet zone = white
    px = img.load()

    # anchors: 4x4 blocks
    for name, (r0, c0) in ANCHOR_CELLS.items():
        color = ANCHOR_PURE[name]
        for r in range(r0, r0 + 4):
            for c in range(c0, c0 + 4):
                for dy in range(scale):
                    for dx in range(scale):
                        px[c * scale + dx, r * scale + dy] = color

    # payload: 1 = black, 0 = white
    for i, bit in enumerate(bits):
        if bit:
            r, c = frame_bit_to_cell(i)
            for dy in range(scale):
                for dx in range(scale):
                    px[c * scale + dx, r * scale + dy] = (0, 0, 0)
    return img
