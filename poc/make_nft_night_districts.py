"""Night Districts #12 — sealed-artwork NFT mock.

Generates a pixel-art night alley in which the big neon sign IS a real,
scannable SV-0001 static frame carrying a signed certificate (collection,
serial, traits, rarity rank, base-art hash). Then verifies the final
composited artwork by decoding it back through the reference receiver
(PNG + JPEG-robustness variant) and exports raw RGBA for the JS decoder.

Scene palette deliberately avoids the anchor HSV bands (cyan 85-95,
magenta 145-155, yellow 25-35, red 0-5/175-179, S>=204 V>=204) so the
decoder locks onto the seal's anchors only.

Run:  .venv/Scripts/python.exe make_nft_night_districts.py
"""

from __future__ import annotations

import hashlib
import io
import json
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from svcode.codec import Encoder, Decoder
from svcode.crypto import key_from_hex, pubkey_hex, vk_from_hex, sha256
from svcode.envelope import Envelope
from svcode.render import render_frame
from svcode.stream import parse_stream

BASE = 512          # scene drawn at BASE x BASE, upscaled x2
OUT = Path(__file__).parent / "nft"
RNG = random.Random(12012)

# ---------------------------------------------------------------- artwork

NAVY_TOP = (7, 10, 26)
NAVY_BOT = (26, 20, 52)
MOON = (232, 234, 246)
AMBER = (255, 183, 77)
ORANGE = (255, 152, 0)
PINK = (240, 98, 146)
VIOLET = (179, 136, 255)
BLUE = (41, 98, 255)
GREEN = (0, 230, 118)
DARK = (10, 13, 24)


def vgrad(draw, box, c0, c1):
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0 - 1)
        draw.line([(x0, y), (x1, y)], fill=tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3)))


def glow(img, cx, cy, r, color, alpha):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(r * 0.55))
    img.alpha_composite(layer)


def draw_scene() -> Image.Image:
    img = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)

    # sky
    vgrad(d, (0, 0, BASE, 210), NAVY_TOP, NAVY_BOT)
    # stars (desaturated -> never in anchor ranges)
    for _ in range(110):
        x, y = RNG.randint(0, BASE - 1), RNG.randint(0, 200)
        b = RNG.randint(120, 230)
        d.point((x, y), fill=(b, b, min(255, b + 12), 255))
    # moon + halo (craters fully inside the disc)
    mx, my, mr = 96, 62, 22
    glow(img, mx, my, mr * 3, MOON, 46)
    d.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=MOON + (255,))
    d.ellipse([mx - 10, my - 8, mx - 1, my + 1], fill=(205, 208, 228, 255))
    d.ellipse([mx + 2, my + 3, mx + 9, my + 10], fill=(205, 208, 228, 255))

    # far skyline
    x = 0
    while x < BASE:
        w, h = RNG.randint(28, 64), RNG.randint(60, 130)
        d.rectangle([x, 210 - h, x + w, 210], fill=(13, 17, 32, 255))
        x += w + RNG.randint(2, 8)

    # alley buildings (left tall, right mid — sign sits on the right one)
    d.rectangle([0, 150, 150, BASE], fill=(12, 15, 28, 255))      # left block
    d.rectangle([150, 210, 210, BASE], fill=(15, 18, 34, 255))    # mid-left
    d.rectangle([360, 120, BASE, BASE], fill=(14, 17, 32, 255))   # right block
    # windows: amber/blue, sparse, muted (S<204 keeps them out of masks)
    for bx0, bx1, by0 in [(8, 142, 165), (158, 202, 225), (368, 504, 135)]:
        for wy in range(by0, BASE - 20, 26):
            for wx in range(bx0, bx1 - 10, 20):
                if RNG.random() < 0.42:
                    c = AMBER if RNG.random() < 0.7 else BLUE
                    dim = RNG.uniform(0.35, 1.0)
                    cc = tuple(int(v * dim) for v in c)
                    d.rectangle([wx, wy, wx + 9, wy + 13], fill=cc + (255,))
    # vertical banner signs (anchor-safe hues) with glow
    banners = [(152, 240, 16, 90, ORANGE), (206, 260, 12, 120, PINK), (352, 150, 12, 100, GREEN)]
    for bx, by, bw, bh, col in banners:
        glow(img, bx + bw // 2, by + bh // 2, bw * 2, col, 40)
        d.rectangle([bx, by, bx + bw, by + bh], fill=tuple(int(v * 0.85) for v in col) + (255,))
        for i in range(3):
            yy = by + 12 + i * (bh // 3)
            d.rectangle([bx + 3, yy, bx + bw - 3, yy + 6], fill=(10, 10, 16, 255))

    # street (perspective trapezoid) + wet reflections
    d.polygon([(150, BASE), (360, BASE), (300, 330), (215, 330)], fill=(16, 19, 32, 255))
    for col, cx in [(ORANGE, 168), (PINK, 240), (VIOLET, 320), (GREEN, 356), (BLUE, 280)]:
        for i in range(26):
            y = 336 + i * 6 + RNG.randint(-2, 2)
            w = max(2, 14 - i // 2)
            a = max(8, 60 - i * 2)
            d.line([(cx - w // 2 + RNG.randint(-3, 3), y), (cx + w // 2 + RNG.randint(-3, 3), y)],
                   fill=col + (a,), width=2)
    # rain — varied length, angle, density
    for _ in range(520):
        x, y = RNG.randint(0, BASE), RNG.randint(0, BASE)
        ln = RNG.choice([4, 5, 6, 8, 10, 13, 17])
        dx = RNG.choice([1, 1, 2, 2, 3])
        d.line([(x, y), (x - dx, y + ln)], fill=(170, 180, 210, RNG.randint(12, 46)), width=1)
    # mist band
    glow(img, BASE // 2, 330, 90, (120, 130, 180), 22)
    return img


def add_vignette(img: Image.Image) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([-BASE * 0.25, -BASE * 0.25, BASE * 1.25, BASE * 1.25], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(60))
    dark = Image.new("RGBA", img.size, (4, 5, 12, 255))
    return Image.composite(img, dark, mask)


# ---------------------------------------------------------------- seal + cert

SIGN_BOX = (176, 128, 176 + 300, 128 + 300)   # sign backing rect in base coords
SEAL_OFF = (SIGN_BOX[0] + 22, SIGN_BOX[1] + 22)


def build() -> None:
    OUT.mkdir(exist_ok=True)
    base = add_vignette(draw_scene()).convert("RGB")
    base_path = OUT / "night-districts-12_base.png"
    base_up = base.resize((BASE * 2, BASE * 2), Image.NEAREST)
    base_up.save(base_path)
    art_hash = hashlib.sha256(base_up.tobytes()).hexdigest()[:16]

    cert = {
        "collection": "night-districts",
        "piece": 12, "supply": 100,
        "traits": {"weather": "rain", "district": "shibuya",
                   "palette": "cyan-magenta", "sign": "flickering"},
        "rarity_rank": 9,
        "art": art_hash,
    }
    payload = json.dumps(cert, separators=(",", ":")).encode()
    assert len(payload) <= 227, f"cert too big for static frame: {len(payload)}"

    sk = key_from_hex(sha256(b"night districts studio artist key v1 (demo)").hex())
    pub = pubkey_hex(sk)
    env = Envelope(target_id=0x4E465431, action=0xA47C, nonce=1759600000, payload=payload)
    env.sign(sk)
    enc = Encoder(env.serialize())
    assert enc.static, "must fit one static frame"
    seed, bits = enc.frame_bits(0)
    seal = render_frame(bits, scale=4)  # 256x256

    # composite: bloom -> beam -> face -> rods -> rim -> spill
    final = base.convert("RGBA")
    x0, y0, x1, y1 = SIGN_BOX
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2

    # 0. sign face canvas + BIG bloom (60px bleed all around)
    face = Image.new("RGB", (x1 - x0, y1 - y0), (5, 7, 13))
    face.paste(seal, (SEAL_OFF[0] - x0, SEAL_OFF[1] - y0))
    bc = Image.new("RGB", (x1 - x0 + 120, y1 - y0 + 120), (5, 7, 13))
    bc.paste(face, (60, 60))
    bloom = bc.filter(ImageFilter.GaussianBlur(30)).convert("RGBA")
    ba = bloom.convert("L").point(lambda v: min(255, int(v * 1.15)))
    bloom.putalpha(ba)
    big = Image.new("RGBA", final.size, (0, 0, 0, 0))
    big.paste(bloom, (x0 - 60, y0 - 60))
    final = Image.alpha_composite(final, big)

    # 1. gantry beam across the alley (bright enough to read as steel)
    d = ImageDraw.Draw(final)
    beam_y0, beam_y1 = y0 - 40, y0 - 28
    d.rectangle([148, beam_y0, BASE, beam_y1], fill=(64, 72, 92, 255))
    d.rectangle([148, beam_y0, BASE, beam_y0 + 3], fill=(110, 120, 148, 255))

    # 2. sharp sign face
    final.paste(face, (x0, y0))

    # 3. hanger rods OVER beam bottom and face top edge (plate area only)
    d = ImageDraw.Draw(final)
    for rx in (x0 + 40, x1 - 40):
        d.rectangle([rx - 3, beam_y1, rx + 3, y0 + 4], fill=(90, 100, 125, 255))
        d.rectangle([rx - 5, beam_y1 - 2, rx + 5, beam_y1 + 2], fill=(110, 120, 148, 255))

    # 4. neon rim + strong outer glow
    d.rectangle(SIGN_BOX, outline=VIOLET + (255,), width=3)
    rim = Image.new("RGBA", final.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    rd.rectangle([x0 - 5, y0 - 5, x1 + 5, y1 + 5], outline=VIOLET + (190,), width=8)
    final = Image.alpha_composite(final, rim.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(final)
    d.rectangle(SIGN_BOX, outline=VIOLET + (255,), width=3)

    # 5. light spill + street reflection (unmistakable)
    spill = Image.new("RGBA", final.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(spill)
    sd.rectangle([x1 + 1, y0 + 6, min(BASE, x1 + 46), y1 - 6], fill=(220, 210, 255, 112))
    sd.rectangle([max(0, x0 - 46), y0 + 20, x0 - 1, y1 - 20], fill=(220, 210, 255, 88))
    sd.ellipse([cx - 120, y1 - 4, cx + 120, y1 + 60], fill=(179, 136, 255, 44))  # magenta smear
    for i in range(34):  # smeared reflection under the sign
        yy = y1 + 6 + i * 5
        w = max(6, 120 - i * 3)
        col = (235, 230, 255, max(10, 90 - i * 2)) if i % 3 else (179, 136, 255, max(10, 70 - i * 2))
        sd.line([(cx - w // 2 + RNG.randint(-5, 5), yy), (cx + w // 2 + RNG.randint(-5, 5), yy)],
                fill=col, width=4)
    final = Image.alpha_composite(final, spill.filter(ImageFilter.GaussianBlur(2))).convert("RGB")

    final_up = final.resize((BASE * 2, BASE * 2), Image.NEAREST)
    final_path = OUT / "night-districts-12.png"
    final_up.save(final_path)
    jpg_path = OUT / "night-districts-12_q80.jpg"
    final_up.save(jpg_path, quality=80)

    # raw RGBA export for the JS decoder harness
    rgba = final_up.convert("RGBA").tobytes()
    (OUT / "night-districts-12.rgba").write_bytes(rgba)

    meta = {
        "title": "Night Districts #12",
        "artist_pubkey": pub,
        "target_id": "0x4E465431", "action": "0xA47C",
        "payload_len": len(payload), "K": enc.k, "seed": seed,
        "cert": cert, "final_png": final_path.name,
    }
    (OUT / "night-districts-12.json").write_text(json.dumps(meta, indent=2))

    # ---------------- self-verify: decode the composited artwork ----------------
    ok_png = verify(final_path, pub, payload)
    ok_jpg = verify(jpg_path, pub, payload)
    print(json.dumps({
        "artist_pubkey": pub, "payload_bytes": len(payload), "K": enc.k,
        "art_hash": art_hash, "decode_png": ok_png, "decode_jpeg_q80": ok_jpg,
        "files": [str(final_path), str(base_path), str(jpg_path)],
    }, indent=2))
    if not ok_png:
        raise SystemExit("DECODE FAILED on the composited PNG")


def verify(path: Path, pub: str, payload: bytes) -> bool:
    try:
        bits = __import__("svcode.decode", fromlist=["decode_file"]).decode_file(str(path))
        dec = Decoder()
        content = dec.feed_bits(bits)
        if content is None:
            print(f"  [{path.name}] LT solve incomplete")
            return False
        env = Envelope.parse(content)
        sig_ok = env.verify(vk_from_hex(pub))
        cert_ok = env.payload == payload
        print(f"  [{path.name}] action=0x{env.action:04X} "
              f"sig={'VALID' if sig_ok else 'INVALID'} cert={'MATCH' if cert_ok else 'MISMATCH'}")
        return sig_ok and cert_ok
    except Exception as e:  # noqa: BLE001
        print(f"  [{path.name}] decode error: {e}")
        return False


if __name__ == "__main__":
    build()
