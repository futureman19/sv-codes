"""Night Districts #15 'Bonsai' — sealed-artwork mock #4 (picture-in-matrix).

The matrix itself becomes the art: each cell's fill is modulated by a 52x52
bonsai reference (dark cells: 20%-100% fill, light cells: 0-30% dot), while
the decoder's central-50% majority vote still reads every bit correctly.
Squint: a tree. Scan: a certificate. Carries LSB shard 3 of 3.

Self-check: PNG + JPEG-q80 decode (sig VALID, cert byte-exact) + shard.
Run:  python make_nft_night_bonsai.py
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import struct

from PIL import Image, ImageDraw, ImageFilter

from svcode.codec import Encoder, Decoder
from svcode.crypto import key_from_hex, pubkey_hex, vk_from_hex, sha256 as sv_sha256
from svcode.envelope import Envelope
from svcode.frame import frame_bit_to_cell, GRID, OFFSET, INNER
from svcode.decode import decode_file

BASE = 512
CELL = 5                       # px per matrix cell (base canvas)
GX0, GY0 = 78, 96              # matrix origin (the scroll panel)
GW = GRID * CELL               # 320
FLOOR = 452

INK = (16, 16, 24)
PAPER = (242, 234, 216)
MOSS_TINT = (206, 228, 190)    # light cells inside foliage
POT_TINT = (232, 206, 188)     # light cells inside the pot
NAVY_TOP = (7, 9, 22)
NAVY_BOT = (20, 24, 44)
MOON = (242, 229, 201)
ANCHOR_HUES = {"tl": (0, 255, 255), "tr": (255, 0, 255),
               "bl": (255, 255, 0), "br": (255, 0, 0)}

ARTIST_SK = key_from_hex(sv_sha256(b"night districts studio artist key v1 (demo)").hex())
ARTIST_PUB = pubkey_hex(ARTIST_SK)

SHARD_MSG = (b"NIGHT DISTRICTS TREASURE | shard 3 of 3 | bonsai-15 | "
             b"three shards, one root - the district is complete")


# ------------------------------------------------------ bonsai reference

def bonsai_reference() -> list[list[float]]:
    """52x52 grid of tree-ness: 1.0 = tree/pot, 0.0 = sky. Hand-grown, seeded."""
    rng = random.Random(1515)
    ref = [[0.0] * INNER for _ in range(INNER)]

    def blob(cx, cy, rx, ry, v, jitter=0.15):
        for r in range(INNER):
            for c in range(INNER):
                dd = ((c - cx) / rx) ** 2 + ((r - cy) / ry) ** 2
                if dd <= 1.0:
                    ref[r][c] = max(ref[r][c], v - rng.random() * jitter)

    # foliage pads (three clouds) + apex
    blob(26, 14, 13, 6, 1.0)
    blob(17, 21, 9, 5, 1.0)
    blob(36, 21, 9, 5, 1.0)
    blob(26, 8, 6, 4, 1.0)
    # trunk: wavy vertical, thicker at base
    for r in range(24, 43):
        t = (r - 24) / 19
        cx = 26 + int(round(2.2 * math.sin(t * 2.4)))
        w = 1 if t < 0.5 else 2
        for c in range(cx - w, cx + w + 1):
            if 0 <= c < INNER:
                ref[r][c] = 1.0
    # branch stubs into pads
    for (r0, c0, r1, c1) in ((26, 24, 22, 18), (26, 28, 22, 35)):
        steps = 6
        for i in range(steps + 1):
            r = r0 + (r1 - r0) * i // steps
            c = c0 + (c1 - c0) * i // steps
            ref[r][c] = 1.0
    # pot: trapezoid
    for r in range(43, 49):
        t = (r - 43) / 5
        half = int(9 - 3 * t)
        for c in range(26 - half, 26 + half + 1):
            ref[r][c] = 1.0
    # soil line + feet
    for c in range(18, 35):
        ref[43][c] = 1.0
    for c in (19, 20, 32, 33):
        ref[49][c] = 1.0
    return ref


# ---------------------------------------------------------------- scene

def render_base_scene() -> Image.Image:
    rng = random.Random(1516)
    img = Image.new("RGB", (BASE, BASE), NAVY_BOT)
    d = ImageDraw.Draw(img)

    for y in range(FLOOR):
        t = y / FLOOR
        d.line([(0, y), (BASE, y)],
               fill=tuple(int(NAVY_TOP[i] * (1 - t) + NAVY_BOT[i] * t) for i in range(3)))
    for _ in range(110):
        x, y = rng.randint(0, BASE - 1), rng.randint(0, 260)
        b = rng.choice((70, 110, 150))
        d.point((x, y), fill=(b, b, min(255, b + 18)))

    mcx, mcy, mr = 428, 84, 24
    halo = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse([mcx - mr - 14, mcy - mr - 14, mcx + mr + 14, mcy + mr + 14],
                                 fill=(242, 229, 201, 20))
    img = Image.alpha_composite(img.convert("RGBA"), halo.filter(ImageFilter.GaussianBlur(11))).convert("RGB")
    d = ImageDraw.Draw(img)
    d.ellipse([mcx - mr, mcy - mr, mcx + mr, mcy + mr], fill=MOON)

    # dark pine silhouettes behind the garden
    for px, ph in ((30, 120), (470, 140), (495, 100)):
        d.polygon([(px - 26, FLOOR - 40), (px, FLOOR - 40 - ph), (px + 26, FLOOR - 40)],
                  fill=(10, 14, 22))
        d.polygon([(px - 18, FLOOR - 70), (px, FLOOR - 70 - ph // 2), (px + 18, FLOOR - 70)],
                  fill=(12, 16, 26))

    # raked sand garden
    for y in range(FLOOR - 40, BASE):
        t = (y - (FLOOR - 40)) / (BASE - (FLOOR - 40))
        d.line([(0, y), (BASE, y)], fill=(int(34 + 8 * t), int(32 + 8 * t), int(44 + 8 * t)))
    for i in range(7):  # rake arcs around the scroll stand
        y0 = FLOOR - 26 + i * 9
        d.arc([40 - i * 3, y0, 430 + i * 3, y0 + 26], start=10, end=170,
              fill=(46, 44, 58))

    # stone lantern, right side, warm amber glow (hue ~18: off anchor bands)
    lx = 438
    d.rectangle([lx - 8, FLOOR - 58, lx + 8, FLOOR - 40], fill=(30, 32, 44))
    d.polygon([(lx - 14, FLOOR - 58), (lx, FLOOR - 72), (lx + 14, FLOOR - 58)], fill=(24, 26, 38))
    d.rectangle([lx - 5, FLOOR - 54, lx + 5, FLOOR - 44], fill=(255, 178, 74))
    lamp = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    ImageDraw.Draw(lamp).ellipse([lx - 26, FLOOR - 70, lx + 26, FLOOR - 28],
                                 fill=(255, 178, 74, 42))
    img = Image.alpha_composite(img.convert("RGBA"), lamp.filter(ImageFilter.GaussianBlur(12))).convert("RGB")

    return img


# ------------------------------------------------------------- matrix

def paint_scroll(img: Image.Image, bits: list[int], ref: list[list[float]]) -> Image.Image:
    """Hanging scroll with the picture-modulated matrix. bit 1 -> ink square
    sized 45%-100% of cell by tree-ness; bit 0 -> empty or a small dot."""
    img = img.convert("RGBA")
    d = ImageDraw.Draw(img)

    # wooden stand + scroll paper
    d.rectangle([GX0 - 22, GY0 + GW - 6, GX0 + GW + 22, GY0 + GW + 34], fill=(26, 18, 12))
    d.rectangle([GX0 - 22, GY0 + GW + 30, GX0 - 14, GY0 + GW + 88], fill=(22, 15, 10))
    d.rectangle([GX0 + GW + 14, GY0 + GW + 30, GX0 + GW + 22, GY0 + GW + 88], fill=(22, 15, 10))
    d.rectangle([GX0 - 14, GY0 - 26, GX0 + GW + 14, GY0 + GW + 8], fill=PAPER + (255,))
    d.rectangle([GX0 - 14, GY0 - 26, GX0 + GW + 14, GY0 - 20], fill=(52, 34, 22, 255))  # top rod
    d.rectangle([GX0 - 14, GY0 + GW, GX0 + GW + 14, GY0 + GW + 8], fill=(52, 34, 22, 255))

    anchor_cells = set()
    for (r0, c0) in ((0, 0), (0, GRID - 4), (GRID - 4, 0), (GRID - 4, GRID - 4)):
        for r in range(r0, r0 + 4):
            for c in range(c0, c0 + 4):
                anchor_cells.add((r, c))
    payload = {}
    for i, b in enumerate(bits):
        payload[frame_bit_to_cell(i)] = b

    for r in range(GRID):
        for c in range(GRID):
            x, y = GX0 + c * CELL, GY0 + r * CELL
            if (r, c) in anchor_cells:
                corner = ("tl" if r < 8 and c < 8 else "tr" if r < 8 else
                          "bl" if c < 8 else "br")
                d.rectangle([x, y, x + CELL - 1, y + CELL - 1],
                            fill=ANCHOR_HUES[corner] + (255,))
                continue
            if (r, c) not in payload:
                continue  # paper margin
            t = ref[r - OFFSET][c - OFFSET]
            # zone tint first (under the ink), moss for canopy / terracotta for pot
            if t > 0.4:
                zone = MOSS_TINT if r - OFFSET < 42 else POT_TINT
                d.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=zone + (60,))
            if payload[(r, c)] == 1:
                # 3 ink tones, integer sides only (float coords rasterize badly).
                # side 3 = canonical 6px = exactly the decoder's sample span -> safe floor.
                side = 3 if t < 0.33 else (4 if t < 0.66 else CELL)
                o = (CELL - side) // 2
                d.rectangle([x + o, y + o, x + o + side - 1, y + o + side - 1],
                            fill=INK + (255,))
            elif t > 0.5:                       # single dot: canonical 2px = 11% sample
                d.point((x + CELL // 2, y + CELL // 2), fill=INK + (255,))
    return img


# ----------------------------------------------------------- LSB shard

def lsb_embed(img: Image.Image, msg: bytes) -> Image.Image:
    img = img.convert("RGB")
    px = img.load()
    data = struct.pack(">I", len(msg)) + msg
    bitstr = "".join(f"{byte:08b}" for byte in data)
    i = 0
    for y in range(img.height):
        for x in range(img.width):
            if i >= len(bitstr):
                return img
            r, g_, b = px[x, y]
            px[x, y] = ((r & ~1) | int(bitstr[i]),
                        (g_ & ~1) | int(bitstr[i + 1]) if i + 1 < len(bitstr) else g_,
                        (b & ~1) | int(bitstr[i + 2]) if i + 2 < len(bitstr) else b)
            i += 3
    raise ValueError("image too small for shard")


def lsb_extract(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    bits: list[str] = []
    n = None
    for y in range(img.height):
        for x in range(img.width):
            r, g, b = img.getpixel((x, y))
            bits += [str(r & 1), str(g & 1), str(b & 1)]
            if n is None and len(bits) >= 32:
                n = struct.unpack(">I", bytes(int("".join(bits[j:j + 8]), 2)
                                              for j in range(0, 32, 8)))[0]
            if n is not None and len(bits) >= 32 + 8 * n:
                return bytes(int("".join(bits[32 + k * 8:40 + k * 8]), 2)
                             for k in range(n))
    raise ValueError("no shard found")


# --------------------------------------------------------------- main

def main() -> None:
    base = render_base_scene()
    art_hash = hashlib.sha256(base.tobytes()).hexdigest()[:16]

    cert = json.dumps({
        "collection": "night-districts",
        "piece": 15,
        "supply": 100,
        "traits": {"weather": "still", "district": "arashiyama",
                   "palette": "ink-moss", "sign": "bloom"},
        "rarity_rank": 1,
        "art": art_hash,
    }, separators=(",", ":")).encode()
    assert len(cert) <= 227, f"cert too big for static frame: {len(cert)}"

    e = Envelope(target_id=0x4E465431, action=0xA47C, nonce=1759630000, payload=cert)
    e.sign(ARTIST_SK)
    enc = Encoder(e.serialize())
    assert enc.static, "must fit one static frame"
    _, bits = enc.frame_bits(0)

    art = paint_scroll(base, bits, bonsai_reference())

    # vignette + grain (below the seal's safety margins: panel ink is deep black
    # on bright paper — vignette dimming stays far from Otsu's split)
    vin = Image.new("L", (BASE, BASE), 0)
    ImageDraw.Draw(vin).ellipse([-130, -130, BASE + 130, BASE + 130], fill=255)
    vin = vin.filter(ImageFilter.GaussianBlur(70))
    dark = Image.new("RGBA", (BASE, BASE), (2, 3, 10, 255))
    art = Image.composite(art, dark, vin)
    rng = random.Random(1517)
    gr = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gr)
    for _ in range(1500):
        x, y = rng.randint(0, BASE - 1), rng.randint(0, BASE - 1)
        v = rng.randint(0, 255)
        gd.point((x, y), fill=(v, v, v, rng.randint(4, 10)))
    art = Image.alpha_composite(art, gr).convert("RGB")

    art_up = art.resize((BASE * 2, BASE * 2), Image.NEAREST)
    art_up = lsb_embed(art_up, SHARD_MSG)

    png = "nft/night-districts-15.png"
    jpg = "nft/night-districts-15.jpg"
    base.save("nft/night-districts-15_base.png")
    art_up.save(png)
    art_up.convert("RGB").save(jpg, quality=80)
    open("nft/night-districts-15.rgba", "wb").write(art_up.convert("RGBA").tobytes())
    json.dump({"artist_pubkey": ARTIST_PUB, "cert": json.loads(cert)},
              open("nft/night-districts-15.json", "w"))
    print(f"artwork: {png}  base-hash: {art_hash}")

    for path in (png, jpg):
        got = decode_file(path)
        dec = Decoder()
        content = dec.feed_bits(got)
        assert content is not None, f"stream incomplete: {path}"
        e2 = Envelope.parse(content)
        ok = e2.verify(vk_from_hex(ARTIST_PUB))
        match = e2.payload == cert
        print(f"[{path.split('/')[-1]}] sig: {'VALID' if ok else 'INVALID'}  cert: {'MATCH' if match else 'MISMATCH'}")
        assert ok and match, path

    shard = lsb_extract(png)
    assert shard == SHARD_MSG, f"LSB mismatch: {shard!r}"
    print(f"lsb shard: OK ({len(shard)} bytes) -> {shard.decode()!r}")
    print("night-districts #15 verified: the bonsai matrix decodes from PNG and JPEG.")


if __name__ == "__main__":
    main()
