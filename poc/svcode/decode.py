"""SV-0001 receiver pipeline (§6): camera image -> 2,704-bit payload matrix.

Steps (normative per spec):
    1. HSV color masking against the four anchor ranges
    2. Centroid extraction via spatial moments
    3. Homography warp to a canonical 64x64 (scaled x10 for subpixel sampling)
    4. Per-cell majority-vote binarization (Otsu-adaptive threshold)
"""

from __future__ import annotations

import cv2
import numpy as np

from .frame import FRAME_BITS, GRID, INNER, OFFSET

WARP_SCALE = 10  # canonical image is 640x640 (10 px per cell)

# §2.1 HSV ranges, OpenCV hue scale 0-179, S/V in 0-255 (>=80% -> >=204)
ANCHOR_HSV = {
    "tl": [(np.array([85, 204, 204]), np.array([95, 255, 255]))],
    "tr": [(np.array([145, 204, 204]), np.array([155, 255, 255]))],
    "bl": [(np.array([25, 204, 204]), np.array([35, 255, 255]))],
    "br": [
        (np.array([0, 204, 204]), np.array([5, 255, 255])),
        (np.array([175, 204, 204]), np.array([179, 255, 255])),
    ],
}

# Canonical anchor centers in warped-image pixels.
# A 4x4 anchor block spanning cells 0..3 covers [0,4) in cell coordinates,
# so its center is at 2.0 cells; the far anchors (cells 60..63) center at 62.0.
_A = 2.0 * WARP_SCALE  # 20.0
_B = 62.0 * WARP_SCALE  # 620.0
CANONICAL_CENTERS = {
    "tl": (_A, _A),
    "tr": (_B, _A),
    "bl": (_A, _B),
    "br": (_B, _B),
}

MIN_ANCHOR_AREA = 30  # px; below this a mask is noise


class DecodeError(ValueError):
    pass


def _centroid(mask: np.ndarray) -> tuple[float, float] | None:
    m = cv2.moments(mask, binaryImage=True)
    if m["m00"] < MIN_ANCHOR_AREA:
        return None
    return (m["m10"] / m["m00"], m["m01"] / m["m00"])


def find_anchors(bgr: np.ndarray) -> dict[str, tuple[float, float]]:
    """Locate the four chromatic anchors. Raises DecodeError if any missing."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    anchors: dict[str, tuple[float, float]] = {}
    for name, ranges in ANCHOR_HSV.items():
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lo, hi in ranges:
            mask |= cv2.inRange(hsv, lo, hi)
        c = _centroid(mask)
        if c is None:
            raise DecodeError(f"anchor {name} not found")
        anchors[name] = c
    return anchors


def warp_canonical(bgr: np.ndarray, anchors: dict[str, tuple[float, float]]) -> np.ndarray:
    """Perspective-warp the grid to a canonical (64*WARP_SCALE)^2 gray image."""
    src = np.array([anchors[k] for k in ("tl", "tr", "bl", "br")], dtype=np.float32)
    dst = np.array([CANONICAL_CENTERS[k] for k in ("tl", "tr", "bl", "br")], dtype=np.float32)
    h, _ = cv2.findHomography(src, dst)
    size = GRID * WARP_SCALE
    warped = cv2.warpPerspective(bgr, h, (size, size))
    return cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)


def extract_bits(gray: np.ndarray) -> list[int]:
    """Read the 52x52 payload matrix from a canonical gray image."""
    payload = gray[
        OFFSET * WARP_SCALE : (OFFSET + INNER) * WARP_SCALE,
        OFFSET * WARP_SCALE : (OFFSET + INNER) * WARP_SCALE,
    ]
    # Otsu threshold on the payload region (adapts to screen brightness)
    theta, _ = cv2.threshold(payload, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bits = [0] * FRAME_BITS
    margin = WARP_SCALE // 4  # sample central 50% of each cell
    span = WARP_SCALE - 2 * margin
    for i in range(FRAME_BITS):
        r, c = OFFSET + i // INNER, OFFSET + i % INNER
        y0 = r * WARP_SCALE + margin
        x0 = c * WARP_SCALE + margin
        block = gray[y0 : y0 + span, x0 : x0 + span]
        dark_fraction = float(np.mean(block < theta))
        bits[i] = 1 if dark_fraction > 0.5 else 0
    return bits


def decode_image(bgr: np.ndarray) -> list[int]:
    """Full pipeline: BGR image -> 2,704 payload bits. Raises DecodeError."""
    anchors = find_anchors(bgr)
    gray = warp_canonical(bgr, anchors)
    return extract_bits(gray)


def decode_file(path: str) -> list[int]:
    img = cv2.imread(path)
    if img is None:
        raise DecodeError(f"cannot read image: {path}")
    return decode_image(img)
