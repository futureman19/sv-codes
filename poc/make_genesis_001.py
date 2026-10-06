"""SV-GENESIS piece #001 — the reference collectible for SV-0002.

TWO artifacts from ONE certificate:
  1. genesis-001-code.png   — the collectible: artwork that IS the SV Code
     (full-bleed 64x64 matrix, sword motif carried in the per-cell tone
     channel per the Night Districts #15 rules — integer rasterization,
     bit-1 fill >= 60%, bit-0 decor dots <= 25% of cell, anchors own the
     pure hues).
  2. genesis-001-reveal.png — the canonical reveal render: a procedural
     blade generated deterministically from (item, seed). Its hash is the
     cert's `art` field. Any engine re-derives it from the same seed.

Cert: SV-0002 canonical JSON, mint = 64 zero hex (pre-mint placeholder).
Self-check: Python decode of code PNG + JPEG-q80 (sig VALID, cert MATCH).
Run:  python make_genesis_001.py
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time

from PIL import Image, ImageDraw, ImageFilter

from svcode.codec import Encoder, Decoder
from svcode.crypto import key_from_hex, pubkey_hex, vk_from_hex, sha256 as sv_sha256
from svcode.envelope import Envelope
from svcode.frame import frame_bit_to_cell, GRID, OFFSET, INNER
from svcode.decode import decode_file

# ------------------------------------------------------------ collection
ISSUER_SK = key_from_hex(sv_sha256(b"sv genesis collection issuer key v1 (demo)").hex())
ISSUER_PUB = pubkey_hex(ISSUER_SK)
ACTION_ITEM_CERT = 0xA47C
TARGET_GENESIS = 0x47454E31            # "GEN1"
SEED_HEX = "a91f3c"                    # piece #001's generation seed
MINT_PENDING = "00" * 32               # pre-mint placeholder (spec 4.1)

CANVAS = 1024
CELL = CANVAS // GRID                  # 16 px per matrix cell, full bleed

# ------------------------------------------------------------ cert helpers

def canonical(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()

# ------------------------------------------------------------ the reveal
# Deterministic procedural blade from (item, seed). Traits are DERIVED here
# and duplicated into the cert per spec 6.

def reveal_params(seed_hex: str) -> dict:
    b = hashlib.sha256(bytes.fromhex(seed_hex)).digest()   # deterministic expansion
    forms = ["long", "bastard", "katana", "claymore"]
    edges = ["straight", "wave", "serrated"]
    cores = ["ember", "azure", "verdant", "umbral"]
    guards = ["swept", "straight", "claw"]
    return {
        "form": forms[b[0] % len(forms)],
        "edge": edges[b[1] % len(edges)],
        "core": cores[b[2] % len(cores)],
        "guard": guards[(b[0] ^ b[1]) % len(guards)],
        "length": 0.55 + (b[3] / 255) * 0.17,    # blade length factor (hilt must fit)
        "glow": 0.55 + (b[4] / 255) * 0.40,      # core glow intensity
    }

CORE_COLORS = {"ember": (255, 122, 40), "azure": (90, 170, 255),
               "verdant": (90, 220, 140), "umbral": (170, 110, 230)}


def render_reveal(seed_hex: str, path: str) -> str:
    p = reveal_params(seed_hex)
    W = H = CANVAS
    img = Image.new("RGB", (W, H), (9, 11, 20))
    d = ImageDraw.Draw(img, "RGBA")
    # starfield backdrop
    rng = random.Random(int(seed_hex, 16))
    for _ in range(180):
        x, y = rng.randrange(W), rng.randrange(H)
        v = rng.randrange(60, 200)
        d.point((x, y), fill=(v, v, min(255, v + 30)))
    cx = W // 2
    top = int(H * 0.08)
    blade_len = int(H * p["length"])
    base_y = top + blade_len
    half_w = {"long": 46, "bastard": 54, "katana": 34, "claymore": 62}[p["form"]]
    core = CORE_COLORS[p["core"]]

    # blade silhouette (curve for katana, wave for wave edge)
    def blade_edge(t):                       # t: 0 tip .. 1 base
        w = half_w * (t ** 0.85)
        xoff = int(26 * math.sin(t * math.pi)) if p["form"] == "katana" else 0
        return cx - xoff, w

    pts_l, pts_r = [], []
    for i in range(65):
        t = i / 64
        xoff, w = blade_edge(t)
        y = top + int(t * blade_len)
        if p["edge"] == "wave":
            w *= 1 + 0.16 * math.sin(t * 22)
        elif p["edge"] == "serrated":
            w *= 1 + (0.22 if (i % 6) < 3 else -0.10)
        pts_l.append((xoff - w, y)); pts_r.append((xoff + w, y))
    d.polygon(pts_l + pts_r[::-1], fill=(148, 158, 178))

    # brushed shading + central fuller
    for i in range(1, 64, 2):
        t = i / 64
        xoff, w = blade_edge(t)
        y = top + int(t * blade_len)
        d.line([(xoff - w, y), (xoff + w, y)], fill=(128, 138, 158))
    for i in range(6, 60):
        t = i / 64
        xoff, w = blade_edge(t)
        y = top + int(t * blade_len)
        d.line([(xoff - 3, y), (xoff + 3, y)], fill=(108, 118, 140))
    # bright bevels
    d.line(pts_l, fill=(212, 220, 236), width=3)
    d.line(pts_r, fill=(212, 220, 236), width=3)

    # core channel glowing down the fuller: wide halo + solid core line
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for i in range(10, 58):
        t = i / 64
        xoff, _ = blade_edge(t)
        y = top + int(t * blade_len)
        g.ellipse([xoff - 14, y - 14, xoff + 14, y + 14],
                  fill=core + (int(150 * p["glow"]),))
    img = Image.alpha_composite(img.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(10, 58):
        t = i / 64
        xoff, _ = blade_edge(t)
        y = top + int(t * blade_len)
        d.line([(xoff, y), (xoff, y + blade_len // 64 + 1)],
               fill=core + (int(230 * p["glow"]),), width=4)

    # guard
    gy = base_y
    gw = {"straight": 150, "swept": 190, "claw": 130}[p["guard"]]
    if p["guard"] == "swept":
        d.polygon([(cx - 8, gy), (cx + 8, gy), (cx + gw, gy - 26), (cx + gw, gy - 12)], fill=(70, 58, 40))
        d.polygon([(cx - 8, gy), (cx + 8, gy), (cx - gw, gy - 26), (cx - gw, gy - 12)], fill=(70, 58, 40))
    elif p["guard"] == "claw":
        d.rectangle([cx - gw, gy - 8, cx + gw, gy + 4], fill=(70, 58, 40))
        d.polygon([(cx - gw, gy - 8), (cx - gw + 26, gy - 34), (cx - gw + 40, gy - 8)], fill=(70, 58, 40))
        d.polygon([(cx + gw, gy - 8), (cx + gw - 26, gy - 34), (cx + gw - 40, gy - 8)], fill=(70, 58, 40))
    else:
        d.rectangle([cx - gw, gy - 6, cx + gw, gy + 6], fill=(70, 58, 40))
    d.rectangle([cx - gw, gy - 2, cx + gw, gy + 2], fill=(120, 100, 66))
    # grip + pommel
    d.rectangle([cx - 12, gy + 8, cx + 12, gy + 96], fill=(34, 30, 34))
    for yy in range(gy + 12, gy + 96, 8):
        d.line([(cx - 12, yy), (cx + 12, yy)], fill=(58, 50, 52))
    d.ellipse([cx - 22, gy + 96, cx + 22, gy + 134], fill=(70, 58, 40))
    d.ellipse([cx - 10, gy + 108, cx + 10, gy + 126], fill=core)

    img.convert("RGB").save(path)
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


# ------------------------------------------- code artwork (picture-in-matrix)

def sword_reference() -> list[list[float]]:
    """52x52 sword-ness: 1.0 blade/guard/grip, 0.45 halo, 0.0 field. Seeded."""
    ref = [[0.0] * INNER for _ in range(INNER)]

    def setv(r, c, v):
        if 0 <= r < INNER and 0 <= c < INNER:
            ref[r][c] = max(ref[r][c], v)

    # blade cols 24-27, rows 6-37 with tip taper rows 2-5
    for r in range(2, 38):
        t = (r - 2) / 36
        half = 1 if t < 0.14 else 2
        for c in range(26 - half, 26 + half + 1):
            setv(r, c, 1.0)
    # fuller line (keeps bit cells readable: carved, not filled)
    for r in range(8, 36):
        ref[r][26] = max(0.0, ref[r][26] - 0.6)
    # crossguard row 39, cols 17-34
    for c in range(17, 35):
        setv(39, c, 1.0); setv(38, c, 1.0)
    # grip rows 41-47, pommel rows 48-50
    for r in range(41, 48):
        setv(r, 25, 1.0); setv(r, 26, 1.0)
    for r in range(48, 51):
        for c in range(24, 28):
            setv(r, c, 1.0)
    # halo around the blade (mid-tone texture)
    for r in range(4, 40):
        for c in range(20, 32):
            if ref[r][c] == 0.0 and any(ref[rr][cc] == 1.0
                                        for rr in range(max(0, r - 2), min(INNER, r + 3))
                                        for cc in range(max(0, c - 2), min(INNER, c + 3))):
                ref[r][c] = 0.45
    return ref


def build_code_art(bits: list[int], path: str):
    """Full-bleed matrix; sword motif rides the tone channel. #15 rules:
    integer rasterization; bit-1 fill side >= 60% of cell; bit-0 dots small;
    scene carries NO pure cyan/magenta/yellow/red outside the anchors."""
    ref = sword_reference()
    img = Image.new("RGB", (CANVAS, CANVAS), (176, 184, 202))
    d = ImageDraw.Draw(img)
    STEEL = (198, 206, 222)        # bright payload field (bit 0 base)
    INK = (18, 22, 34)             # bit-1 ink (dark; decoder: 1 = DARK)
    INK_SOFT = (52, 62, 84)        # bit-1 ink on halo cells — still below Otsu
    HALO = (168, 178, 200)
    GOLD = (120, 100, 62)

    # pass 1: every cell — anchors, quiet zone, payload bases
    for r in range(GRID):
        for c in range(GRID):
            x, y = c * CELL, r * CELL
            corner = (r < 4 or r >= GRID - 4) and (c < 4 or c >= GRID - 4)
            if corner:
                hue = {(0, 0): (0, 255, 255), (0, GRID - 4): (255, 0, 255),
                       (GRID - 4, 0): (255, 255, 0), (GRID - 4, GRID - 4): (255, 0, 0)}[
                    (0 if r < 4 else GRID - 4, 0 if c < 4 else GRID - 4)]
                d.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=hue)
            elif r < 6 or r >= GRID - 6 or c < 6 or c >= GRID - 6:
                pass                                      # quiet zone = canvas bg
            else:
                v = ref[r - OFFSET][c - OFFSET]
                d.rectangle([x, y, x + CELL - 1, y + CELL - 1],
                            fill=STEEL if v < 0.4 else HALO)

    # pass 2: payload ink / decor dots (integer rasterization only)
    for i, bit in enumerate(bits):
        r, c = OFFSET + i // INNER, OFFSET + i % INNER
        x, y = c * CELL, r * CELL
        v = ref[i // INNER][i % INNER]
        cxp, cyp = x + CELL // 2, y + CELL // 2
        if bit == 1:
            side = {0.0: 10, 0.45: 11}.get(v, 0) or (13 if v < 1.0 else 16)
            side = max(10, min(CELL, side))           # >= 62% of 16px cell
            h = side // 2
            d.rectangle([cxp - h, cyp - h, cxp - h + side - 1, cyp - h + side - 1],
                        fill=INK if v >= 1.0 else INK_SOFT)
        else:
            dsize = 4 if v >= 1.0 else (3 if v >= 0.4 else 0)
            if dsize:
                dd = dsize // 2
                tint = GOLD if v >= 1.0 else (140, 150, 172)
                d.rectangle([cxp - dd, cyp - dd, cxp - dd + dsize - 1, cyp - dd + dsize - 1],
                            fill=tint)
    img.save(path)


# ------------------------------------------------------------ pipeline

def main():
    t0 = time.time()
    reveal_path = "nft/genesis-001-reveal.png"
    art_hash = render_reveal(SEED_HEX, reveal_path)
    p = reveal_params(SEED_HEX)

    cert = {"art": art_hash, "col": "sv-genesis", "ed": 1, "item": "genesis-blade",
            "mint": MINT_PENDING, "of": 100, "seed": SEED_HEX,
            "tr": {"core": p["core"], "edge": p["edge"]}, "v": 2}
    cert_bytes = canonical(cert)
    assert len(cert_bytes) <= 227, f"cert over budget: {len(cert_bytes)}"
    print(f"cert {len(cert_bytes)}B  art {art_hash}  traits {cert['tr']}")

    e = Envelope(target_id=TARGET_GENESIS, action=ACTION_ITEM_CERT,
                 nonce=int(time.time()), payload=cert_bytes)
    e.sign(ISSUER_SK)
    enc = Encoder(e.serialize())
    assert enc.static, "must fit one static frame"
    _, bits = enc.frame_bits(0)

    code_path = "nft/genesis-001-code.png"
    build_code_art(bits, code_path)
    Image.open(code_path).convert("RGB").save("nft/_genesis-001.jpg", quality=80)
    open("nft/genesis-001-code.rgba", "wb").write(Image.open(code_path).convert("RGBA").tobytes())

    # self-check: Python decode of PNG + JPEG-q80
    for probe in (code_path, "nft/_genesis-001.jpg"):
        got = decode_file(probe)
        content = Decoder().feed_bits(got)
        assert content is not None, f"stream incomplete: {probe}"
        e2 = Envelope.parse(content)
        ok_sig = e2.verify(vk_from_hex(ISSUER_PUB))
        ok_cert = e2.payload == cert_bytes
        print(f"[{probe.split('/')[-1]}] sig: {'VALID' if ok_sig else 'INVALID'}  "
              f"cert: {'MATCH' if ok_cert else 'MISMATCH'}")
        assert ok_sig and ok_cert

    meta = {"cert": json.loads(cert_bytes), "cert_sha256": hashlib.sha256(cert_bytes).hexdigest(),
            "issuer_pub": ISSUER_PUB, "action": ACTION_ITEM_CERT,
            "target_id": TARGET_GENESIS, "reveal_params": p}
    json.dump(meta, open("nft/genesis-001-cert.json", "w"), indent=2)
    print(f"genesis-001 built in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
