"""Night Districts #14 'Rooftop' — sealed-artwork mock #3 (diegetic tier).

The seal shrinks to hanko scale: a small SV sticker on the rooftop parapet,
bottom-right — the artist's seal in the corner of the print. Measured floor
for the digital pipeline: 1px cells (128px on a 1024 canvas) still decode
through JPEG q60; this piece ships at the floor: 1px cells (128px on 1024), bare, bottom-right.

Self-check: PNG + JPEG-q80 decode (sig VALID, cert byte-exact) + LSB shard 2.
Run:  python make_nft_night_rooftop.py
"""

from __future__ import annotations

import hashlib
import json
import random
import struct

from PIL import Image, ImageDraw, ImageFilter

from svcode.codec import Encoder, Decoder
from svcode.crypto import key_from_hex, pubkey_hex, vk_from_hex, sha256 as sv_sha256
from svcode.envelope import Envelope
from svcode.render import render_frame
from svcode.decode import decode_file

BASE = 512
SEAL_SCALE = 1                       # 1px cells = the measured decode floor
SEAL = 64 * SEAL_SCALE               # 64px base / 128px final — bare, no plate
SX, SY = BASE - SEAL - 10, BASE - SEAL - 10   # bottom-right, 20px final inset

NAVY_TOP = (8, 10, 26)
STEEL_BOT = (44, 52, 76)
ROSE = (201, 127, 146)               # muted: S~117, safely off anchor bands
FOG = (180, 190, 205)
MOON = (242, 229, 201)

ARTIST_SK = key_from_hex(sv_sha256(b"night districts studio artist key v1 (demo)").hex())
ARTIST_PUB = pubkey_hex(ARTIST_SK)

SHARD_MSG = (b"NIGHT DISTRICTS TREASURE | shard 2 of 3 | rooftop-14 | "
             b"one sign remains - it blooms, it does not hang")


# ---------------------------------------------------------------- scene

def render_base_scene() -> Image.Image:
    rng = random.Random(1414)
    img = Image.new("RGB", (BASE, BASE), STEEL_BOT)
    d = ImageDraw.Draw(img)

    HORIZON = 356
    for y in range(HORIZON):
        t = y / HORIZON
        c = tuple(int(NAVY_TOP[i] * (1 - t) + STEEL_BOT[i] * t) for i in range(3))
        if y > HORIZON - 70:  # rose band bleeding up from the horizon
            rt = (y - (HORIZON - 70)) / 70
            c = tuple(int(c[i] * (1 - 0.45 * rt) + ROSE[i] * 0.45 * rt) for i in range(3))
        d.line([(0, y), (BASE, y)], fill=c)

    for _ in range(130):  # stars
        x, y = rng.randint(0, BASE - 1), rng.randint(0, 220)
        b = rng.choice((70, 110, 150))
        d.point((x, y), fill=(b, b, min(255, b + 18)))

    mcx, mcy, mr = 118, 92, 26
    halo = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse([mcx - mr - 16, mcy - mr - 16, mcx + mr + 16, mcy + mr + 16],
                                 fill=(242, 229, 201, 20))
    img = Image.alpha_composite(img.convert("RGBA"),
                                halo.filter(ImageFilter.GaussianBlur(12))).convert("RGB")
    d = ImageDraw.Draw(img)
    d.ellipse([mcx - mr, mcy - mr, mcx + mr, mcy + mr], fill=MOON)
    for _ in range(4):
        r = rng.randint(2, 6)
        cx, cy = mcx + rng.randint(-12, 9), mcy + rng.randint(-11, 9)
        d.ellipse([cx, cy, cx + r, cy + r], fill=(213, 199, 165))

    # --- district vista: three haze layers of skyline
    layers = [(0.55, (58, 66, 88), 300, 90), (0.75, (38, 44, 64), 322, 120),
              (1.0, (22, 26, 44), 344, 150)]
    for _, shade, base_y, maxh in layers:
        x = -10
        while x < BASE + 10:
            w = rng.randint(28, 64)
            h = rng.randint(30, maxh)
            d.rectangle([x, base_y - h, x + w, base_y], fill=shade)
            if shade == (22, 26, 44):  # nearest layer gets sparse windows
                for _ in range(w * h // 700):
                    wx = rng.randint(x + 2, max(x + 2, x + w - 4))
                    wy = rng.randint(base_y - h + 4, base_y - 6)
                    d.point((wx, wy), fill=rng.choice(((70, 78, 100), (150, 110, 60))))
            x += w + rng.randint(4, 14)

    # our Facade #13 tower, mid-distance — amber grid easter egg (dim, decorative)
    fx, fw, ftop = 296, 44, 214
    d.rectangle([fx, ftop, fx + fw, 344], fill=(16, 19, 36))
    for wy in range(ftop + 4, 340, 5):
        for wx in range(fx + 3, fx + fw - 3, 5):
            if rng.random() < 0.42:
                d.rectangle([wx, wy, wx + 2, wy + 2], fill=(150, 102, 44))

    # --- fog band rolling over the city
    fog = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fog)
    for i in range(5):
        y0 = 330 + i * 18
        fd.rectangle([0, y0, BASE, y0 + 34], fill=FOG + (16 + i * 7,))
    img = Image.alpha_composite(img.convert("RGBA"),
                                fog.filter(ImageFilter.GaussianBlur(14))).convert("RGB")

    # --- rooftop foreground: parapet + railing + two figures + AC unit
    d = ImageDraw.Draw(img)
    PARA = 452
    d.rectangle([0, PARA, BASE, BASE], fill=(10, 11, 20))           # parapet slab
    d.rectangle([0, PARA, BASE, PARA + 3], fill=(28, 30, 46))       # ledge highlight
    d.line([(0, PARA - 22), (BASE, PARA - 22)], fill=(36, 40, 58), width=2)  # top rail
    for x in range(8, BASE, 24):                                    # balusters
        d.line([(x, PARA - 22), (x, PARA)], fill=(30, 34, 50), width=1)

    def figure(fx0, fh):
        d.ellipse([fx0 + 3, PARA - 22 - fh, fx0 + 11, PARA - 14 - fh], fill=(8, 9, 16))
        d.polygon([(fx0, PARA), (fx0 + 2, PARA - 14 - fh + 8), (fx0 + 12, PARA - 14 - fh + 8),
                   (fx0 + 14, PARA)], fill=(8, 9, 16))

    figure(150, 34)
    figure(172, 30)

    d.rectangle([392, PARA - 16, 424, PARA], fill=(14, 16, 28))     # AC unit
    d.rectangle([394, PARA - 14, 422, PARA - 12], fill=(24, 26, 40))

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
        "piece": 14,
        "supply": 100,
        "traits": {"weather": "fog", "district": "koenji",
                   "palette": "steel-rose", "sign": "hanko"},
        "rarity_rank": 2,
        "art": art_hash,
    }, separators=(",", ":")).encode()
    assert len(cert) <= 227, f"cert too big for static frame: {len(cert)}"

    e = Envelope(target_id=0x4E465431, action=0xA47C, nonce=1759625000, payload=cert)
    e.sign(ARTIST_SK)
    enc = Encoder(e.serialize())
    assert enc.static, "must fit one static frame"
    _, bits = enc.frame_bits(0)
    seal = render_frame(bits, scale=SEAL_SCALE).convert("RGBA")  # 64x64
    # soften pure white to warm paper — same luminance headroom, less stark
    px = seal.load()
    for yy in range(seal.height):
        for xx in range(seal.width):
            r, g, b, a = px[xx, yy]
            if (r, g, b) == (255, 255, 255):
                px[xx, yy] = (242, 234, 216, a)

    # vignette + grain FIRST (seal stays pristine)
    art = base.convert("RGBA")
    vin = Image.new("L", (BASE, BASE), 0)
    ImageDraw.Draw(vin).ellipse([-130, -130, BASE + 130, BASE + 130], fill=255)
    vin = vin.filter(ImageFilter.GaussianBlur(70))
    dark = Image.new("RGBA", (BASE, BASE), (2, 3, 10, 255))
    art = Image.composite(art, dark, vin)
    rng = random.Random(1415)
    gr = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gr)
    for _ in range(1500):
        x, y = rng.randint(0, BASE - 1), rng.randint(0, BASE - 1)
        v = rng.randint(0, 255)
        gd.point((x, y), fill=(v, v, v, rng.randint(4, 10)))
    art = Image.alpha_composite(art, gr)

    # the bare seal, pasted last — no plate, no frame: the white quiet zone
    # of the matrix IS the margin, like paper around a signature
    art.paste(seal, (SX, SY))
    art = art.convert("RGB")

    art_up = art.resize((BASE * 2, BASE * 2), Image.NEAREST)
    art_up = lsb_embed(art_up, SHARD_MSG)

    png = "nft/night-districts-14.png"
    jpg = "nft/night-districts-14.jpg"
    base.save("nft/night-districts-14_base.png")
    art_up.save(png)
    art_up.convert("RGB").save(jpg, quality=80)
    open("nft/night-districts-14.rgba", "wb").write(art_up.convert("RGBA").tobytes())
    json.dump({"artist_pubkey": ARTIST_PUB, "cert": json.loads(cert)},
              open("nft/night-districts-14.json", "w"))
    print(f"artwork: {png}  base-hash: {art_hash}  seal: {SEAL}px base / {SEAL*2}px final")

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
    print("night-districts #14 verified: hanko seal decodes from PNG and JPEG.")


if __name__ == "__main__":
    main()
