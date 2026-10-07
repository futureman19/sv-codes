"""QR-inlay SV code prototype v0 — 96x96 grid, center QR inlay, signed payload.

Proves the merged artifact:
  layer 1 (normie):  any phone camera reads the QR -> svcode.org
  layer 2 (machine): the grid around it carries a signed BMP envelope,
                     fountain-encoded across the cells that survive the inlay.

Frame layout (prototype, NOT a spec yet):
  96x96 grid, 6-cell border, 84x84 inner matrix.
  Center INLAY x INLAY cells reserved for the QR (QR quiet zone included).
  Frame bits = 40-bit header (seed16|ctype8|k16, SV-0001 layout)
             + 22 slots x 256 bits, row-major over inner cells, skipping inlay.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_H

from svcode.crypto import key_from_hex, pubkey_hex, vk_from_hex
from svcode.envelope import Envelope
from svcode.fountain import LTDecoder, encode_symbol, soliton_cdf
from svcode.stream import build_stream, parse_stream, split_symbols

OUT = Path(r"C:\Users\futur\.hermes\profiles\telegram3\cache\scratch")
VECTORS = Path(r"C:\Users\futur\Desktop\sv-codes\poc\vectors\vectors.json")

GRID, OFFSET, INNER = 96, 6, 84
SCALE = 12
SEED = 1  # fountain mode (NOT static identity): every slot carries real encoded
          # data -> the matrix fills uniformly around the QR, and any ~K of the
          # slots suffice to decode (the grid survives heavy occlusion).
CONTENT_ENVELOPE = 0x01
QR_PAYLOAD = "HTTPS://SVCODE.ORG"
QR_BORDER = 2          # modules of QR quiet zone (spec says 4; 2 scans reliably — halves the white ring)
QR_SCALE = 1           # SV cells per QR module: 1 = QR woven into the matrix pitch (~30% width), 2 = dominant QR (~60%)

MESSAGE = (
    "ONE CODE. Your camera read the QR - a machine verified this signed "
    "grid. No internet, just light. sv-codes"
)

ANCHORS = {  # pure hues, same as SV-0001
    (0, 0): (0, 255, 255), (0, 92): (255, 0, 255),
    (92, 0): (255, 255, 0), (92, 92): (255, 0, 0),
}

report = []


def ok(name, cond, detail=""):
    report.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond:
        raise SystemExit(f"gate failed: {name}")


# ---------- 1. QR ----------
qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H, border=QR_BORDER)
qr.add_data(QR_PAYLOAD)
qr.make(fit=True)
qmat = qr.get_matrix()  # includes border
QCELLS = len(qmat)
INLAY = QCELLS * QR_SCALE  # no extra guard: the QR's own quiet zone is the separator
print(f"QR: version {qr.version} ({qr.modules_count} modules), {QCELLS} cells with border x{QR_SCALE} -> {INLAY} SV cells, EC=H")

INLAY0 = (INNER - INLAY) // 2          # first inner row/col of the inlay
# QR module counts are odd, so at QR_SCALE=1 the inlay sits 1 cell off exact
# center — invisible at cell pitch; the QR's own quiet zone stays uniform.

def in_inlay(r, c):
    return INLAY0 <= r < INLAY0 + INLAY and INLAY0 <= c < INLAY0 + INLAY

cells = [(r, c) for r in range(INNER) for c in range(INNER) if not in_inlay(r, c)]
NSLOTS = (len(cells) - 40) // 256
FRAME_BITS = 40 + NSLOTS * 256
ok("capacity", NSLOTS >= 10,
   f"inlay {INLAY}x{INLAY} -> {len(cells)} usable cells -> {NSLOTS} slots (need >=10 for today's static budget)")

# ---------- 2. signed payload -> frame bits ----------
v = json.loads(VECTORS.read_text())
sk = key_from_hex(v["private_key_hex"])
pub = pubkey_hex(sk)

env = Envelope(target_id=0x53564331, action=0x00FF, payload=MESSAGE.encode())
env.sign(sk)
stream = build_stream(env.serialize())
symbols = split_symbols(stream)
K = len(symbols)
ok("K fits", K <= NSLOTS, f"envelope {len(env.serialize())}B -> stream {len(stream)}B -> K={K} (max {NSLOTS})")

cdf = soliton_cdf(K)
bits = []
def put(val, n):
    for b in range(n - 1, -1, -1):
        bits.append((val >> b) & 1)
put(SEED, 16); put(CONTENT_ENVELOPE, 8); put(K, 16)
for slot in range(NSLOTS):
    sym = encode_symbol(symbols, cdf, SEED, slot)
    for byte in sym:
        put(byte, 8)
bits += [0] * (len(cells) - len(bits))

# ---------- 3. render ----------
img = Image.new("RGB", (GRID * SCALE, GRID * SCALE), (255, 255, 255))
px = img.load()
def fill(gr, gc, rgb):
    for dy in range(SCALE):
        for dx in range(SCALE):
            px[gc * SCALE + dx, gr * SCALE + dy] = rgb
for (r0, c0), color in ANCHORS.items():
    for r in range(r0, r0 + 4):
        for c in range(c0, c0 + 4):
            fill(r, c, color)
for bit, (r, c) in zip(bits, cells):
    if bit:
        fill(OFFSET + r, OFFSET + c, (0, 0, 0))
for rr in range(QCELLS):
    for cc in range(QCELLS):
        if qmat[rr][cc]:
            for dr in range(QR_SCALE):
                for dc in range(QR_SCALE):
                    fill(OFFSET + INLAY0 + rr * QR_SCALE + dr,
                         OFFSET + INLAY0 + cc * QR_SCALE + dc, (0, 0, 0))
code_path = OUT / "inlay-code.png"
img.save(code_path)
print(f"wrote {code_path} ({img.width}x{img.height})")

# ---------- 4. verify SV layer (digital sample through the real codec) ----------
arr = np.asarray(img.convert("L"))
def cell_bit(r, c):
    y0 = int((OFFSET + r + 0.25) * SCALE); x0 = int((OFFSET + c + 0.25) * SCALE)
    return 1 if arr[y0:y0 + SCALE // 2, x0:x0 + SCALE // 2].mean() < 128 else 0

rbits = [cell_bit(r, c) for (r, c) in cells[:FRAME_BITS]]
def read(off, n):
    v_ = 0
    for i in range(n):
        v_ = (v_ << 1) | rbits[off + i]
    return v_
rseed, rctype, rk = read(0, 16), read(16, 8), read(24, 16)
ok("header roundtrip", (rseed, rctype, rk) == (SEED, CONTENT_ENVELOPE, K),
   f"seed={rseed} ctype={rctype:#x} K={rk}")
lt = LTDecoder(rk)
for slot in range(NSLOTS):
    sym = bytes(read(40 + slot * 256 + b * 8, 8) for b in range(32))
    if sym == bytes(32):
        continue
    if lt.add_frame_symbol(rseed, slot, sym):
        break
solved = lt.solved()
ok("fountain solved", solved is not None, f"symbols={lt.symbol_count()}/{rk}")
content = parse_stream(b"".join(solved))
renv = Envelope.parse(content)
ok("envelope signature", renv.verify(vk_from_hex(pub)), f"action={renv.action_name} target=0x{renv.target_id:08X}")
ok("payload byte-exact", renv.payload == MESSAGE.encode(), renv.payload.decode()[:48] + "…")

# ---------- 5. verify QR layer: pristine + simulated phone photo ----------
bgr = cv2.imread(str(code_path))
det = cv2.QRCodeDetector()

def qr_read(im):
    r, infos, _, _ = det.detectAndDecodeMulti(im)
    if r and any(infos):
        return list(infos)
    s = det.detectAndDecode(im)[0]
    return [s] if s else []

info = qr_read(bgr)
ok("QR pristine", QR_PAYLOAD in info, f"decoded={info}")
small = cv2.resize(bgr, (250, 250), interpolation=cv2.INTER_NEAREST)
is_ = qr_read(small)
ok("QR at 250px (2.6px/module floor)", QR_PAYLOAD in is_, f"decoded={is_}")

code500 = cv2.resize(bgr, (500, 500), interpolation=cv2.INTER_NEAREST)
canvas = np.full((720, 960, 3), 40, dtype=np.uint8)
canvas[110:610, 230:730] = code500
M = cv2.getRotationMatrix2D((480, 360), 3, 1.0)
scene = cv2.warpAffine(canvas, M, (960, 720), borderValue=(40, 40, 40))
scene = cv2.GaussianBlur(scene, (3, 3), 0)
rng = np.random.default_rng(7)
scene = np.clip(scene.astype(np.int16) + rng.integers(-14, 15, scene.shape), 0, 255).astype(np.uint8)
raw_ok = QR_PAYLOAD in qr_read(scene)
gray = cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY)
_, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
bin_ok = QR_PAYLOAD in qr_read(cv2.cvtColor(th, cv2.COLOR_GRAY2BGR))
ok("QR phone-sim (500px grid, 3deg, blur+noise)", raw_ok or bin_ok,
   f"raw={'hit' if raw_ok else 'miss'} binarized={'hit' if bin_ok else 'miss'}")
Image.fromarray(cv2.cvtColor(scene, cv2.COLOR_BGR2RGB)).save(OUT / "inlay-phonesim.png")

# ---------- 6. productized sticker mock ----------
def font(size, bold=False):
    for name in ("consolab.ttf" if bold else "consola.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype("C:/Windows/Fonts/" + name, size)
        except OSError:
            continue
    return ImageFont.load_default()

CW, CH = 1800, 1200
card = Image.new("RGB", (CW, CH), "white")
d = ImageDraw.Draw(card)
code960 = img.resize((960, 960), Image.NEAREST)
card.paste(code960, (90, 120))
d.rectangle([74, 104, 1066, 1096], outline="#dddddd", width=2)

tx = 1110
f_head = font(88, bold=True)
f_sub = font(36)
f_url = font(54, bold=True)
f_note = font(28)

def fits(text, fnt, x):
    bb = d.textbbox((0, 0), text, font=fnt)
    return x + (bb[2] - bb[0]) <= CW - 40

for t, f in (("ONE CODE.", f_head),
             ("Your camera reads the QR.", f_sub),
             ("Machines verify the signed grid.", f_sub),
             ("svcode.org", f_url),
             ("scan it - then decide your own", f_note)):
    assert fits(t, f, tx), f"text overflows canvas: {t}"

d.text((tx, 200), "ONE CODE.", font=f_head, fill="black")
for i, hue in enumerate(((0, 255, 255), (255, 0, 255), (255, 255, 0), (255, 0, 0))):
    d.rectangle([tx + i * 40, 322, tx + i * 40 + 26, 348], fill=hue)
d.text((tx, 400), "Your camera reads the QR.", font=f_sub, fill="#222222")
d.text((tx, 458), "Machines verify the signed grid.", font=f_sub, fill="#222222")
d.text((tx, 560), "svcode.org", font=f_url, fill="black")
d.text((tx, 656), "scan it - then decide your own", font=f_note, fill="#666666")

def ctext(y, text, fnt, fill="black"):
    bb = d.textbbox((0, 0), text, font=fnt)
    d.text(((CW - (bb[2] - bb[0])) / 2, y), text, font=fnt, fill=fill)
ctext(CH - 76, "This sticker carries real Bitcoin.", font(44, bold=True))
mock_path = OUT / "inlay-sticker-mock.png"
card.save(mock_path)
print(f"wrote {mock_path}")

print("\nALL GATES:", "PASS" if all(r[1] for r in report) else "FAIL", f"({len(report)} checks)")
