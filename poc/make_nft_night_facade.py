"""Night Districts #13 'Facade' — sealed-artwork mock #2.

The SV Code is hidden one level deeper than #12: the lit windows of a
skyscraper ARE the matrix. Amber-on-navy palette (luminance-binarizable,
per SV-0001 the decoder thresholds on brightness — cells need not be
black/white). The four corner anchors present as architectural corner
lights. An LSB shard rides in the PNG for hunters (dies under JPEG —
documented on the page).

Self-check: decodes the composited PNG AND a JPEG-q80 export, verifies the
signature, compares the certificate byte-for-byte, and round-trips the LSB
shard. Run:  python make_nft_night_facade.py
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
from svcode.frame import frame_bit_to_cell, GRID
from svcode.decode import decode_file

BASE = 512
CELL = 5                       # px per matrix cell (base canvas)
GX0, GY0 = 96, 64              # grid origin on canvas (building face)
GW = GRID * CELL               # 320
FLOOR = 448
STREET = 512

NAVY_TOP = (7, 9, 24)
NAVY_BOT = (24, 19, 48)
FACADE = (13, 17, 34)          # building body
TRIM = (9, 12, 26)             # border-cell panels
WIN_LIT = (255, 178, 74)       # amber window  (bit 0 -> LIGHT)
WIN_LIT_HOT = (255, 214, 140)
WIN_DARK = (22, 27, 48)        # dark window   (bit 1 -> DARK, > facade for texture)
MOON = (242, 229, 201)
ANCHOR_HUES = {  # corner -> pure hue (SV-0001 anchor colours)
    "tl": (0, 255, 255), "tr": (255, 0, 255),
    "bl": (255, 255, 0), "br": (255, 0, 0),
}

ARTIST_SK = key_from_hex(sv_sha256(b"night districts studio artist key v1 (demo)").hex())
ARTIST_PUB = pubkey_hex(ARTIST_SK)


# ---------------------------------------------------------------- scene

def render_base_scene() -> Image.Image:
    rng = random.Random(1313)
    img = Image.new("RGB", (BASE, BASE), NAVY_BOT)
    d = ImageDraw.Draw(img)

    for y in range(FLOOR):
        t = y / FLOOR
        d.line([(0, y), (BASE, y)],
               fill=tuple(int(NAVY_TOP[i] * (1 - t) + NAVY_BOT[i] * t) for i in range(3)))

    for _ in range(120):  # stars
        x, y = rng.randint(0, BASE - 1), rng.randint(0, 300)
        b = rng.choice((70, 110, 150))
        d.point((x, y), fill=(b, b, min(255, b + 18)))

    mcx, mcy, mr = 82, 78, 20   # moon, off to the left
    d.ellipse([mcx - mr, mcy - mr, mcx + mr, mcy + mr], fill=MOON)
    for _ in range(4):          # craters, fully inside the disc
        r = rng.randint(2, 5)
        cx, cy = mcx + rng.randint(-9, 7), mcy + rng.randint(-8, 7)
        d.ellipse([cx, cy, cx + r, cy + r], fill=(213, 199, 165))
    halo = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse([mcx - mr - 14, mcy - mr - 14, mcx + mr + 14, mcy + mr + 14],
                                 fill=(242, 229, 201, 18))
    img.paste(Image.alpha_composite(img.convert("RGBA"), halo.filter(ImageFilter.GaussianBlur(10))).convert("RGB"),
              (0, 0))

    d = ImageDraw.Draw(img)
    # --- skyline silhouettes
    x = 0
    DECOYS = [(0, 190, 190), (190, 0, 190), (190, 190, 0), (190, 40, 40),
              (40, 160, 90), (60, 90, 190)]  # dim roof lights: S/V below anchor masks
    while x < BASE:
        w = rng.randint(34, 70)
        h = rng.randint(120, 250)
        top = FLOOR - h
        shade = rng.choice(((11, 14, 30), (14, 17, 36), (17, 20, 40)))
        d.rectangle([x, top, x + w, FLOOR], fill=shade)
        for _ in range(w * h // 480):  # sparse dim windows on neighbours
            wx, wy = rng.randint(x + 2, x + w - 4), rng.randint(top + 6, FLOOR - 10)
            if rng.random() < 0.35:
                c = rng.choice(((52, 60, 84), (60, 66, 92), (46, 54, 76)))
                d.rectangle([wx, wy, wx + 2, wy + 3], fill=c)
        if rng.random() < 0.45 and w > 40:  # neon roof light — decoy corner lights
            col = rng.choice(DECOYS)
            lx = x + rng.randint(6, w - 10)
            d.rectangle([lx, top - 3, lx + 5, top - 1], fill=col)
            d.line([(lx + 2, top), (lx + 2, top - 3)], fill=(40, 46, 64))
        x += w + rng.randint(2, 10)

    # --- hero tower: dark facade that will host the matrix
    d.rectangle([GX0 - 6, GY0 - 14, GX0 + GW + 6, FLOOR], fill=FACADE)
    d.rectangle([GX0 - 6, GY0 - 14, GX0 + GW + 6, GY0 - 12], fill=(30, 36, 58))  # parapet lip
    for yy in range(GY0, GY0 + GW, CELL):  # faint floor lines every 8 storeys
        if (yy - GY0) % (CELL * 8) == 0:
            d.line([(GX0 - 6, yy), (GX0 + GW + 6, yy)], fill=(18, 23, 42))

    # rooftop antenna + amber beacon (amber hue ~20: safely outside anchor bands)
    ax = GX0 + GW // 2 + 30
    d.line([(ax, GY0 - 14), (ax, GY0 - 52)], fill=(40, 46, 64), width=2)
    d.point((ax, GY0 - 53), fill=(200, 120, 40))
    d.point((ax, GY0 - 54), fill=(160, 90, 30))

    # podium + entrance: canopy slab, double doors, light spill on pavement
    d.rectangle([GX0 - 14, GY0 + GW, GX0 + GW + 14, FLOOR], fill=(11, 14, 30))
    d.rectangle([GX0 + GW // 2 - 34, FLOOR - 30, GX0 + GW // 2 + 34, FLOOR - 27], fill=(24, 28, 46))
    door = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    dd = ImageDraw.Draw(door)
    dd.rectangle([GX0 + GW // 2 - 24, FLOOR - 26, GX0 + GW // 2 + 24, FLOOR], fill=(255, 178, 74, 100))
    dd.rectangle([GX0 + GW // 2 - 24, FLOOR - 26, GX0 + GW // 2 + 24, FLOOR - 26], outline=None)
    dd.polygon([(GX0 + GW // 2 - 26, FLOOR), (GX0 + GW // 2 + 26, FLOOR),
                (GX0 + GW // 2 + 40, FLOOR + 14), (GX0 + GW // 2 - 40, FLOOR + 14)],
               fill=(255, 178, 74, 34))
    img = Image.alpha_composite(img.convert("RGBA"), door).convert("RGB")
    d = ImageDraw.Draw(img)
    d.line([(GX0 + GW // 2, FLOOR - 26), (GX0 + GW // 2, FLOOR)], fill=(20, 16, 30), width=1)

    # annex wing, left of the tower — ordinary sparse windows dilute the grid read
    ax0, ax1, atop = GX0 - 78, GX0 - 14, 296
    d.rectangle([ax0, atop, ax1, FLOOR], fill=(15, 18, 36))
    d.rectangle([ax0, atop, ax1, atop + 2], fill=(26, 31, 50))
    for wy in range(atop + 8, FLOOR - 8, 9):
        for wx in range(ax0 + 5, ax1 - 6, 8):
            if rng.random() < 0.30:
                col = rng.choice(((255, 178, 74), (96, 104, 128), (60, 66, 92)))
                d.rectangle([wx, wy, wx + 3, wy + 4], fill=col)

    # --- street
    d = ImageDraw.Draw(img)
    for y in range(FLOOR, STREET):
        t = (y - FLOOR) / (STREET - FLOOR)
        d.line([(0, y), (BASE, y)], fill=(int(20 - 10 * t), int(19 - 9 * t), int(38 - 18 * t)))
    return img


# ------------------------------------------------------------- matrix

def paint_matrix(img: Image.Image, bits: list[int]) -> Image.Image:
    """Render the 64x64 grid onto the facade. bit 0 -> lit window, bit 1 -> dark.
    Windows are jittered in size/shade/position so the facade reads as organic
    architecture, not a matrix. Anchors = corner beacon lights with halos."""
    img = img.convert("RGBA")
    anchor_cells = set()
    for (r0, c0) in ((0, 0), (0, GRID - 4), (GRID - 4, 0), (GRID - 4, GRID - 4)):
        for r in range(r0, r0 + 4):
            for c in range(c0, c0 + 4):
                anchor_cells.add((r, c))
    payload = {}
    for i, b in enumerate(bits):
        payload[frame_bit_to_cell(i)] = b

    AMBERS = [(255, 178, 74), (255, 190, 92), (255, 168, 60), (247, 196, 110)]
    DIMS = [(22, 27, 48), (18, 23, 42), (26, 31, 54)]

    # glow underlay for lit windows
    glow = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for (r, c), b in payload.items():
        if b == 0:
            x, y = GX0 + c * CELL, GY0 + r * CELL
            g.rectangle([x - 1, y - 1, x + CELL, y + CELL], fill=(255, 178, 74, 46))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(2)))

    d = ImageDraw.Draw(img)
    for r in range(GRID):
        for c in range(GRID):
            x, y = GX0 + c * CELL, GY0 + r * CELL
            if (r, c) in anchor_cells:
                corner = ("tl" if r < 8 and c < 8 else
                          "tr" if r < 8 else
                          "bl" if c < 8 else "br")
                hue = ANCHOR_HUES[corner]
                d.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=hue + (255,))
                continue
            if (r, c) not in payload:
                d.rectangle([x + 1, y + 1, x + CELL - 2, y + CELL - 2], fill=TRIM + (255,))
                continue
            crng = random.Random(13_000 + r * 64 + c)
            w = crng.choice((3, 3, 4))                 # window width variant
            ox = crng.choice((0, 1)) if w == 4 else 1  # horizontal jitter
            oy = crng.choice((0, 1))                   # vertical jitter
            x0w, y0w = x + ox, y + oy
            if payload[(r, c)] == 0:                   # lit (bit 0 -> LIGHT)
                col = crng.choice(AMBERS)
                d.rectangle([x0w, y0w, x0w + w - 1, y0w + w - 1], fill=col + (255,))
                if crng.random() < 0.15:               # curtain: dim the top row
                    d.line([(x0w, y0w), (x0w + w - 1, y0w)], fill=(140, 96, 40, 255))
            else:                                      # dark (bit 1 -> DARK)
                col = crng.choice(DIMS)
                d.rectangle([x0w, y0w, x0w + w - 1, y0w + w - 1], fill=col + (255,))

    # corner-beacon halos (drawn around the anchor blocks, never over them)
    halos = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    h = ImageDraw.Draw(halos)
    for (cx0, cy0, corner) in ((GX0, GY0, "tl"), (GX0 + GW - 20, GY0, "tr"),
                               (GX0, GY0 + GW - 20, "bl"), (GX0 + GW - 20, GY0 + GW - 20, "br")):
        hue = ANCHOR_HUES[corner]
        h.rectangle([cx0 - 6, cy0 - 6, cx0 + 25, cy0 + 25], fill=hue + (64,))
    img = Image.alpha_composite(img, halos.filter(ImageFilter.GaussianBlur(7)))
    return img


# ----------------------------------------------------------- LSB shard

SHARD_MSG = (b"NIGHT DISTRICTS TREASURE | shard 1 of 3 | facade-13 | "
             b"the other two signs hang elsewhere in the district")


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
        "piece": 13,
        "supply": 100,
        "traits": {"weather": "clear", "district": "shinjuku",
                   "palette": "amber-gold", "sign": "window-grid"},
        "rarity_rank": 4,
        "art": art_hash,
    }, separators=(",", ":")).encode()
    assert len(cert) <= 227, f"cert too big for static frame: {len(cert)}"

    e = Envelope(target_id=0x4E465431, action=0xA47C, nonce=1759610000, payload=cert)
    e.sign(ARTIST_SK)
    enc = Encoder(e.serialize())
    assert enc.static, "must fit one static frame"
    _, bits = enc.frame_bits(0)

    art = paint_matrix(base, bits)

    # amber reflection column on the street, under the tower
    refl = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    rd = ImageDraw.Draw(refl)
    rng = random.Random(1314)
    for x in range(GX0, GX0 + GW, 4):
        a = rng.randint(14, 42)
        ln = rng.randint(10, 30)
        rd.line([(x, FLOOR + 2), (x + rng.randint(-1, 1), FLOOR + 2 + ln)],
                fill=(255, 178, 74, a), width=2)
    art = Image.alpha_composite(art, refl.filter(ImageFilter.GaussianBlur(2)))

    # vignette + grain
    vin = Image.new("L", (BASE, BASE), 0)
    vd = ImageDraw.Draw(vin)
    vd.ellipse([-130, -130, BASE + 130, BASE + 130], fill=255)
    vin = vin.filter(ImageFilter.GaussianBlur(70))
    dark = Image.new("RGBA", (BASE, BASE), (2, 3, 10, 255))
    art = Image.composite(art, dark, vin)
    gr = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gr)
    for _ in range(1500):
        x, y = rng.randint(0, BASE - 1), rng.randint(0, BASE - 1)
        v = rng.randint(0, 255)
        gd.point((x, y), fill=(v, v, v, rng.randint(4, 10)))
    art = Image.alpha_composite(art, gr).convert("RGB")

    art_up = art.resize((BASE * 2, BASE * 2), Image.NEAREST)
    art_up = lsb_embed(art_up, SHARD_MSG)

    png = "nft/night-districts-13.png"
    jpg = "nft/night-districts-13.jpg"
    base.save("nft/night-districts-13_base.png")
    art_up.save(png)
    art_up.convert("RGB").save(jpg, quality=80)
    open("nft/night-districts-13.rgba", "wb").write(art_up.convert("RGBA").tobytes())
    open("nft/night-districts-13_cert.json", "wb").write(cert)
    json.dump({"artist_pubkey": ARTIST_PUB, "cert": json.loads(cert)},
              open("nft/night-districts-13.json", "w"))
    print(f"artwork: {png}  base-hash: {art_hash}")

    # ---- self-check: python decode of PNG + JPEG
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
    print("night-districts #13 verified: sealed certificate decodes from PNG and JPEG.")


if __name__ == "__main__":
    main()
