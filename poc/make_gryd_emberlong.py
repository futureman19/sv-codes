"""Grydbound 'Emberlong Sword' — sealed in-game item mock.

One item certificate, two presentations of the same NFT item:
  1. emberlong-standard.png  — item card, bare corner seal (Sealed Signature)
  2. emberlong-legendary.png — hero blade whose glowing runes ARE the matrix
     (texture tier, diegetic: four elemental gems at the blade corners are
     the anchors; rune marks carry the bits)

Self-check: both versions decode from PNG + JPEG q80 (sig VALID, cert
byte-exact, identical cert in both). Run:  python make_gryd_emberlong.py
"""

from __future__ import annotations

import hashlib
import json
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from svcode.codec import Encoder, Decoder
from svcode.crypto import key_from_hex, pubkey_hex, vk_from_hex, sha256 as sv_sha256
from svcode.envelope import Envelope
from svcode.frame import frame_bit_to_cell, GRID, OFFSET, INNER
from svcode.render import render_frame
from svcode.decode import decode_file

BASE = 512
CARD = (14, 14, 22)
PANEL = (22, 24, 36)
GOLD = (168, 138, 74)          # muted: S~143, off anchor bands
BONE = (226, 218, 196)
EMBER = (199, 91, 42)          # H~9.4 S~201: below the red-mask saturation gate
EMBER_DIM = (140, 66, 34)
STEEL = (30, 34, 48)
STEEL_HI = (52, 58, 78)
RUNE_LIT = (255, 232, 192)     # light cells (bit 0): bright center
RUNE_HOT = (255, 178, 74)
ANCHOR_HUES = {"tl": (0, 255, 255), "tr": (255, 0, 255),
               "bl": (255, 255, 0), "br": (255, 0, 0)}

# legendary blade anatomy (base px): rune panel inset, sword-proportioned
BCELL = 2
BGW = GRID * BCELL             # 128 rune panel
BX0, BY0 = (BASE - BGW) // 2, 162
MARGIN = 16                    # steel margin each side of the rune panel
BLX0, BLX1 = BX0 - MARGIN, BX0 + BGW + MARGIN   # blade silhouette edges
POINT_BASE, GUARD_Y = 150, 330
TIP_Y = 40                     # 110px tapered point above the blade body

ARTIST_SK = key_from_hex(sv_sha256(b"grydbound studio armory key v1 (demo)").hex())
ARTIST_PUB = pubkey_hex(ARTIST_SK)

FONT = ImageFont.load_default()


def text(d, xy, s, fill=BONE):
    d.text(xy, s, fill=fill, font=FONT)


# ---------------------------------------------------------------- card

def draw_sword_icon(d, cx, y0, scale=1):
    """Small display sword for the standard card."""
    w = 3 * scale
    # blade: molten gradient
    for i in range(90):
        t = i / 90
        col = tuple(int(RUNE_HOT[k] * (1 - t) + (255, 240, 210)[k] * t) for k in range(3))
        d.rectangle([cx - w, y0 + i, cx + w, y0 + i], fill=col)
    d.polygon([(cx - w, y0), (cx + w, y0), (cx, y0 - 12)], fill=(255, 240, 210))
    d.line([(cx, y0 + 6), (cx, y0 + 84)], fill=EMBER_DIM)           # fuller
    d.rectangle([cx - 26, y0 + 90, cx + 26, y0 + 98], fill=(24, 20, 28))  # guard
    d.rectangle([cx - 26, y0 + 90, cx + 26, y0 + 91], fill=GOLD)
    for j in range(26):                                              # wrapped grip
        d.rectangle([cx - 4, y0 + 98 + j, cx + 4, y0 + 98 + j],
                    fill=(64, 44, 30) if j % 4 < 2 else (48, 32, 22))
    d.ellipse([cx - 7, y0 + 124, cx + 7, y0 + 138], fill=(24, 20, 28))
    d.ellipse([cx - 3, y0 + 128, cx + 3, y0 + 134], fill=EMBER)      # pommel ember


def card_base(title_lines) -> Image.Image:
    rng = random.Random(2323)
    img = Image.new("RGB", (BASE, BASE), (8, 8, 14))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([10, 10, BASE - 10, BASE - 10], radius=10, fill=CARD, outline=GOLD, width=2)
    d.rounded_rectangle([18, 18, BASE - 18, BASE - 18], radius=8, fill=PANEL, outline=(40, 40, 54))
    # ember ambience: dim particles, all V/S under anchor gates
    for _ in range(26):
        x, y = rng.randint(30, BASE - 30), rng.randint(60, BASE - 40)
        v = rng.randint(70, 130)
        d.point((x, y), fill=(v, v // 2, v // 4))
    return img


def finish_card(img: Image.Image, name_y=430) -> Image.Image:
    d = ImageDraw.Draw(img)
    text(d, (34, name_y), "EMBERLONG SWORD", GOLD)
    text(d, (34, name_y + 14), "Two-handed blade · Molten / Obsidian", (150, 148, 160))
    text(d, (34, name_y + 28), "ATK 47   SPD 12", BONE)
    text(d, (34, name_y + 42), "Edition 23 / 500", (150, 148, 160))
    return img


def grain_vignette(img: Image.Image) -> Image.Image:
    img = img.convert("RGBA")
    vin = Image.new("L", (BASE, BASE), 0)
    ImageDraw.Draw(vin).ellipse([-130, -130, BASE + 130, BASE + 130], fill=255)
    vin = vin.filter(ImageFilter.GaussianBlur(70))
    dark = Image.new("RGBA", (BASE, BASE), (2, 3, 10, 255))
    img = Image.composite(img, dark, vin)
    rng = random.Random(2324)
    gr = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gr)
    for _ in range(1200):
        x, y = rng.randint(0, BASE - 1), rng.randint(0, BASE - 1)
        v = rng.randint(0, 255)
        gd.point((x, y), fill=(v, v, v, rng.randint(3, 9)))
    return Image.alpha_composite(img, gr)


# ------------------------------------------------------------- versions

def build_standard(bits, base_img):
    art = grain_vignette(base_img)
    seal = render_frame(bits, scale=1).convert("RGBA")   # 64x64 -> 128px final
    px = seal.load()
    for yy in range(seal.height):                        # soften white to paper
        for xx in range(seal.width):
            r, g, b, a = px[xx, yy]
            if (r, g, b) == (255, 255, 255):
                px[xx, yy] = (242, 234, 216, a)
    art.paste(seal, (BASE - 64 - 14, BASE - 64 - 14))    # bare, pasted last
    return art.convert("RGB")


def build_legendary(bits, base_img):
    art = grain_vignette(base_img)
    d = ImageDraw.Draw(art)
    payload = {frame_bit_to_cell(i): b for i, b in enumerate(bits)}
    anchor_cells = set()
    for (r0, c0) in ((0, 0), (0, GRID - 4), (GRID - 4, 0), (GRID - 4, GRID - 4)):
        for r in range(r0, r0 + 4):
            for c in range(c0, c0 + 4):
                anchor_cells.add((r, c))

    # rune glow underlay (around marks, never over centers)
    glow = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for (r, c), b in payload.items():
        if b == 0:
            x, y = BX0 + c * BCELL, BY0 + r * BCELL
            g.rectangle([x - 1, y - 1, x + BCELL, y + BCELL], fill=RUNE_HOT + (36,))
    art = Image.alpha_composite(art, glow.filter(ImageFilter.GaussianBlur(2)))
    d = ImageDraw.Draw(art)

    ARMS = ((0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (-1, 1))
    for r in range(GRID):
        for c in range(GRID):
            x, y = BX0 + c * BCELL, BY0 + r * BCELL
            cx, cy = x + BCELL // 2, y + BCELL // 2
            if (r, c) in anchor_cells:
                corner = ("tl" if r < 8 and c < 8 else "tr" if r < 8 else
                          "bl" if c < 8 else "br")
                # anchor = a glowing circular gem, not a square: blade continuity
                # around it, hue blob + centroid preserved for the decoder
                d.rectangle([x, y, x + BCELL - 1, y + BCELL - 1], fill=STEEL + (255,))
                continue
            if (r, c) not in payload:
                d.rectangle([x, y, x + BCELL - 1, y + BCELL - 1], fill=STEEL + (255,))
                continue
            arm = ARMS[(r * 64 + c) % len(ARMS)]
            if payload[(r, c)] == 0:                      # lit rune (bit 0 -> BRIGHT cell)
                jitter = 230 + ((r * 64 + c) * 7) % 26    # 230..255 per-cell tone
                lit = (255, min(255, jitter), 200)
                d.rectangle([x, y, x + BCELL - 1, y + BCELL - 1], fill=lit + (255,))
                # etch strokes stay ABOVE the dark/bright threshold: the JS sampler
                # votes sparse points near the cell center; a mid-dark etch there
                # would flip votes. Warm-bright etch = visible rune, safe vote.
                d.point((cx + arm[0], cy + arm[1]), fill=(255, 190, 120, 255))
                if (r * 64 + c) % 5 == 0:                 # second etch: glyph variety
                    d.point((cx - arm[1], cy + arm[0]), fill=(255, 190, 120, 255))
            else:                                          # bare steel (bit 1 -> DARK cell)
                d.rectangle([x, y, x + BCELL - 1, y + BCELL - 1], fill=STEEL + (255,))
                d.point((cx, cy), fill=(38, 40, 54, 255))  # brushed mark

    # circular gem anchors: pure-hue discs at the four panel corners + glow ring
    glow2 = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    g2 = ImageDraw.Draw(glow2)
    for (r0, c0, corner) in ((0, 0, "tl"), (0, GRID - 4, "tr"),
                             (GRID - 4, 0, "bl"), (GRID - 4, GRID - 4, "br")):
        gx = BX0 + c0 * BCELL + 2 * BCELL   # block center
        gy = BY0 + r0 * BCELL + 2 * BCELL
        g2.ellipse([gx - 7, gy - 7, gx + 7, gy + 7], fill=ANCHOR_HUES[corner] + (70,))
    art = Image.alpha_composite(art, glow2.filter(ImageFilter.GaussianBlur(3)))
    d = ImageDraw.Draw(art)
    for (r0, c0, corner) in ((0, 0, "tl"), (0, GRID - 4, "tr"),
                             (GRID - 4, 0, "bl"), (GRID - 4, GRID - 4, "br")):
        gx = BX0 + c0 * BCELL + 2 * BCELL
        gy = BY0 + r0 * BCELL + 2 * BCELL
        hue = ANCHOR_HUES[corner]
        d.ellipse([gx - 4, gy - 4, gx + 4, gy + 4], fill=hue + (255,))
        d.ellipse([gx - 2, gy - 2, gx + 1, gy + 1], fill=tuple(min(255, v + 60) for v in hue) + (255,))
    return art.convert("RGB")


# --------------------------------------------------------------- main

def main() -> None:
    # ---- base card art (shared): frame + ambience; hash it for the cert
    proto = card_base(None)
    d = ImageDraw.Draw(proto)
    # legendary hero blade: silhouette first — long point, bright bevels,
    # ricasso, swept quillons, ringed grip, disc pommel. Rune panel inset later.
    blc = (BLX0 + BLX1) // 2
    d.rectangle([BLX0, POINT_BASE, BLX1, GUARD_Y], fill=STEEL)             # blade body
    # brushed-steel vertical shading
    for yy in range(POINT_BASE, GUARD_Y, 3):
        d.line([(BLX0, yy), (BLX1, yy)], fill=(26, 30, 42))
    # shoulders: blade edges taper inward to the point base (steep, sword-like)
    d.polygon([(BLX0, POINT_BASE), (blc - 48, POINT_BASE), (blc, TIP_Y)], fill=STEEL)
    d.polygon([(BLX1, POINT_BASE), (blc + 48, POINT_BASE), (blc, TIP_Y)], fill=STEEL)
    d.polygon([(blc - 34, POINT_BASE), (blc, TIP_Y + 22), (blc + 34, POINT_BASE)],
              fill=STEEL_HI)                                             # point ridge
    d.line([(blc - 48, POINT_BASE), (blc, TIP_Y)], fill=STEEL_HI, width=2)  # bevels
    d.line([(blc + 48, POINT_BASE), (blc, TIP_Y)], fill=STEEL_HI, width=2)
    d.line([(BLX0, POINT_BASE), (BLX0, GUARD_Y)], fill=STEEL_HI, width=2)
    d.line([(BLX1, POINT_BASE), (BLX1, GUARD_Y)], fill=STEEL_HI, width=2)
    d.line([(blc, POINT_BASE + 8), (blc, BY0 - 6)], fill=EMBER_DIM, width=2)      # fuller above
    d.line([(blc, BY0 + BGW + 6), (blc, GUARD_Y - 6)], fill=EMBER_DIM, width=2)   # fuller in ricasso
    # inscription frame around the rune panel
    d.rectangle([BX0 - 3, BY0 - 3, BX0 + BGW + 3, BY0 + BGW + 3], outline=GOLD)
    # swept quillons: wide curved arms + gold finial caps
    d.polygon([(blc - 6, GUARD_Y - 4), (BLX0 - 48, GUARD_Y - 22), (BLX0 - 44, GUARD_Y - 10),
               (blc - 2, GUARD_Y + 10)], fill=(24, 20, 28))
    d.polygon([(blc + 6, GUARD_Y - 4), (BLX1 + 48, GUARD_Y - 22), (BLX1 + 44, GUARD_Y - 10),
               (blc + 2, GUARD_Y + 10)], fill=(24, 20, 28))
    d.rectangle([BLX0 - 52, GUARD_Y - 26, BLX0 - 42, GUARD_Y - 8], fill=GOLD)
    d.rectangle([BLX1 + 42, GUARD_Y - 26, BLX1 + 52, GUARD_Y - 8], fill=GOLD)
    d.rectangle([blc - 8, GUARD_Y - 2, blc + 8, GUARD_Y + 8], fill=GOLD)   # collar
    # two-hand grip: ringed, gold-collared
    for j in range(64):
        yy = GUARD_Y + 10 + j
        d.rectangle([blc - 6, yy, blc + 6, yy],
                    fill=(64, 44, 30) if (j // 4) % 2 else (48, 32, 22))
    d.rectangle([blc - 6, GUARD_Y + 10, blc + 6, GUARD_Y + 13], fill=GOLD)
    d.rectangle([blc - 6, GUARD_Y + 70, blc + 6, GUARD_Y + 73], fill=GOLD)
    # disc pommel with ember gem
    d.ellipse([blc - 11, GUARD_Y + 74, blc + 11, GUARD_Y + 94], fill=(24, 20, 28))
    d.ellipse([blc - 11, GUARD_Y + 74, blc + 11, GUARD_Y + 94], outline=GOLD)
    d.ellipse([blc - 4, GUARD_Y + 81, blc + 4, GUARD_Y + 89], fill=EMBER)
    proto = finish_card(proto)
    proto.save("nft/emberlong-base.png")
    art_hash = hashlib.sha256(proto.tobytes()).hexdigest()[:16]

    cert = json.dumps({
        "game": "grydbound",
        "item": "emberlong-sword",
        "edition": 23, "supply": 500,
        "stats": {"atk": 47, "spd": 12, "seed": "a91f3c"},
        "traits": {"blade": "molten", "guard": "obsidian"},
        "mint": "a91f3c2e",
        "art": art_hash,
    }, separators=(",", ":")).encode()
    assert len(cert) <= 227, f"cert too big: {len(cert)}"

    e = Envelope(target_id=0x47525944, action=0x17E9, nonce=1759640000, payload=cert)  # target GRYD, GAME ITEM cert
    e.sign(ARTIST_SK)
    enc = Encoder(e.serialize())
    assert enc.static
    _, bits = enc.frame_bits(0)

    std = build_standard(bits, proto)
    leg = build_legendary(bits, proto)
    std_up = std.resize((BASE * 2, BASE * 2), Image.NEAREST)
    leg_up = leg.resize((BASE * 2, BASE * 2), Image.NEAREST)
    std_up.save("nft/emberlong-standard.png")
    leg_up.save("nft/emberlong-legendary.png")
    std_up.save("nft/emberlong-standard.jpg", quality=80)
    leg_up.save("nft/emberlong-legendary.jpg", quality=80)
    open("nft/emberlong-standard.rgba", "wb").write(std_up.convert("RGBA").tobytes())
    open("nft/emberlong-legendary.rgba", "wb").write(leg_up.convert("RGBA").tobytes())
    json.dump({"artist_pubkey": ARTIST_PUB, "cert": json.loads(cert)},
              open("nft/emberlong.json", "w"))
    print(f"cert {len(cert)}B  art hash {art_hash}")

    for path in ("nft/emberlong-standard.png", "nft/emberlong-standard.jpg",
                 "nft/emberlong-legendary.png", "nft/emberlong-legendary.jpg"):
        got = decode_file(path)
        dec = Decoder()
        content = dec.feed_bits(got)
        assert content is not None, f"stream incomplete: {path}"
        e2 = Envelope.parse(content)
        ok = e2.verify(vk_from_hex(ARTIST_PUB))
        match = e2.payload == cert
        print(f"[{path.split('/')[-1]}] sig: {'VALID' if ok else 'INVALID'}  cert: {'MATCH' if match else 'MISMATCH'}")
        assert ok and match, path
    print("emberlong verified: one cert, two presentations, PNG + JPEG.")


if __name__ == "__main__":
    main()
