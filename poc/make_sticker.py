"""make_sticker.py — print-ready SV Codes campaign sticker.

Layout (default 6x3 in @ 300 DPI):
  [ QR code  | YOU SCAN THIS ]  [ SV Code | MACHINES SCAN THIS ]
  tagline + url along the bottom.

The QR carries the landing-page URL (?s=<id> for per-sticker analytics).
The SV grid carries a signed static-frame envelope (the published test
authority, so the site's scanner shows VALID). Message must stay <= 227
payload bytes to keep static print mode (single frame).

Usage:
  python make_sticker.py --id demo1
  python make_sticker.py --id main-st-01 --url https://svcode.org/j/ --message "..."
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from svcode.codec import Encoder
from svcode.crypto import key_from_hex
from svcode.envelope import Envelope
from svcode.render import render_frame

ROOT = Path(__file__).resolve().parent
VECTORS = ROOT / "vectors" / "vectors.json"

DPI = 300
W_IN, H_IN = 6.0, 3.0
W, H = int(W_IN * DPI), int(H_IN * DPI)

DEFAULT_MESSAGE = (
    "HELLO FROM A STICKER. A machine read this grid and verified its "
    "signature — no internet, just light. sv-codes"
)
TAGLINE = "This sticker carries real Bitcoin."
SUBLINE = "scan the left grid with your phone — the right one is for machines"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in ("consolab.ttf" if bold else "consola.ttf", "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf", "arial.ttf"):
        for base in ("C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/", ""):
            try:
                return ImageFont.truetype(base + name, size)
            except OSError:
                continue
    return ImageFont.load_default()


def make_qr(payload: str, box: int) -> Image.Image:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    modules = qr.modules_count + 2 * qr.border
    box_size = max(4, box // modules)
    img = qr.make_image(image_factory=None, fill_color="black", back_color="white")
    img = img.convert("RGB")
    side = modules * box_size
    return img.resize((side, side), Image.NEAREST)


def center_text(draw: ImageDraw.ImageDraw, cx: float, y: float, text: str, fnt, fill="black"):
    bbox = draw.textbbox((0, 0), text, font=fnt)
    tw = bbox[2] - bbox[0]
    draw.text((cx - tw / 2, y), text, font=fnt, fill=fill)


def build_sticker(url: str, sticker_id: str, message: str) -> Image.Image:
    payload_url = f"{url}{'&' if '?' in url else '?'}s={sticker_id}"

    # --- SV side: signed static frame with the published test authority
    v = json.loads(VECTORS.read_text())
    sk = key_from_hex(v["private_key_hex"])
    env = Envelope(target_id=0x53564331, action=0x00FF, payload=message.encode())
    env.sign(sk)
    enc = Encoder(env.serialize())
    if not enc.static:
        raise SystemExit(
            f"message too long: envelope {len(env.serialize())}B exceeds static mode "
            f"(payload must be <= 227 bytes); shorten --message")
    _, bits = enc.frame_bits(0)
    sv_img = render_frame(bits, scale=10).convert("RGB")  # 640x640

    qr_img = make_qr(payload_url, 640)

    # --- canvas
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_cap = font(34, bold=True)
    f_tag = font(40, bold=True)
    f_sub = font(26)

    margin = 50
    cell_w = (W - 2 * margin) // 2
    grid_y = 70
    for i, grid in enumerate((qr_img, sv_img)):
        cx = margin + cell_w * i + cell_w // 2
        side = grid.width
        d.rectangle([cx - side // 2 - 16, grid_y - 16, cx + side // 2 + 15, grid_y + side + 15],
                    outline="#dddddd", width=2)
        img.paste(grid, (cx - side // 2, grid_y))
        center_text(d, cx, grid_y + side + 26, "YOU SCAN THIS" if i == 0 else "MACHINES SCAN THIS", f_cap)

    d.line([W // 2, grid_y + 40, W // 2, grid_y + 600], fill="#dddddd", width=2)

    center_text(d, W / 2, H - 118, TAGLINE, f_tag)
    center_text(d, W / 2, H - 62, f"{payload_url}  ·  {SUBLINE}", f_sub, fill="#444444")
    return img


def main() -> int:
    ap = argparse.ArgumentParser(description="SV Codes campaign sticker generator")
    ap.add_argument("--id", required=True, help="sticker id (analytics), e.g. main-st-01")
    ap.add_argument("--url", default="https://svcode.org/j/",
                    help="landing page URL the QR points to")
    ap.add_argument("--message", default=DEFAULT_MESSAGE, help="SV grid payload (<=227 bytes)")
    ap.add_argument("--out", help="output PNG (default stickers/<id>.png)")
    ap.add_argument("--inlay", action="store_true",
                    help="SV-0005 merged sticker: QR inside the signed grid (human onboarding edition)")
    ap.add_argument("--inlay-url", default="https://svcode.org/i",
                    help="inlay QR target (must stay <=20 alphanumeric chars for the canonical inlay)")
    ap.add_argument("--inlay-message", default=INLAY_MESSAGE, help="inlay grid payload")
    args = ap.parse_args()

    if args.inlay:
        return build_inlay_sticker(args)

    img = build_sticker(args.url, args.id, args.message)
    out = Path(args.out) if args.out else ROOT / "stickers" / f"{args.id}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, dpi=(DPI, DPI))
    print(f"wrote {out} ({W}x{H}px @ {DPI}dpi = {W_IN}x{H_IN} in)")
    print(f"QR payload: {args.url}{'&' if '?' in args.url else '?'}s={args.id}")
    return 0


INLAY_MESSAGE = (
    "YOU FOUND THE MESSAGE INSIDE. This grid is signed - your phone verified "
    "it locally, no server, no internet. Make your own at svcode.org"
)


def build_inlay_sticker(args) -> int:
    """SV-0005 merged artifact + a productized card. Self-verifies both layers."""
    import cv2
    import numpy as np
    from svcode.inlay import (
        decode_inlay_image, encode_inlay_frame, layout_for, render_inlay,
    )
    from svcode.envelope import Envelope as Env

    qr_payload = args.inlay_url.strip().upper()
    layout = layout_for(qr_payload)  # raises if the QR outgrows the canonical inlay
    if layout.qcells > 29:
        raise SystemExit(
            f"QR payload too long: needs {layout.qcells - 8} modules "
            f"(canonical inlay holds v2 = 25). Shorten --inlay-url.")

    v = json.loads(VECTORS.read_text())
    sk = key_from_hex(v["private_key_hex"])
    env = Env(target_id=0x53564331, action=0x00FF, payload=args.inlay_message.encode())
    env.sign(sk)
    bits = encode_inlay_frame(env.serialize(), layout, seed=1)
    code = render_inlay(bits, layout, scale=12).convert("RGB")  # 1152x1152

    # --- gate 1: SV layer roundtrip through the real decoder
    bgr = cv2.cvtColor(np.array(code), cv2.COLOR_RGB2BGR)
    dec = decode_inlay_image(bgr, layout)
    assert dec == bits[: len(dec)], "SV layer: decoded bits differ"
    from svcode.inlay import InlayDecoder
    content = InlayDecoder().feed_bits(dec, layout)
    env2 = Env.parse(content)
    assert env2.payload == args.inlay_message.encode(), "SV layer: payload mismatch"
    print("PASS  SV layer decodes + signature verifies")

    # --- gate 2: QR layer reads
    det = cv2.QRCodeDetector()
    ok, infos, _, _ = det.detectAndDecodeMulti(bgr)
    if not ok or not any(infos):
        s = det.detectAndDecode(bgr)[0]
        infos = [s] if s else []
    assert qr_payload in infos, f"QR layer: read {infos}"
    print(f"PASS  QR layer reads: {qr_payload}")

    # --- productized card (1800x1200)
    CW, CH = 1800, 1200
    card = Image.new("RGB", (CW, CH), "white")
    d = ImageDraw.Draw(card)
    code960 = code.resize((960, 960), Image.NEAREST)
    card.paste(code960, (90, 120))
    d.rectangle([74, 104, 1066, 1096], outline="#dddddd", width=2)
    tx = 1110
    f_head, f_sub, f_url, f_note = font(80, bold=True), font(36), font(54, bold=True), font(28)
    d.text((tx, 200), "ONE STICKER,", font=f_head, fill="black")
    d.text((tx, 300), "TWO LANGUAGES.", font=f_head, fill="black")
    for i, hue in enumerate(((0, 255, 255), (255, 0, 255), (255, 255, 0), (255, 0, 0))):
        d.rectangle([tx + i * 40, 432, tx + i * 40 + 26, 458], fill=hue)
    d.text((tx, 500), "Your camera read the QR.", font=f_sub, fill="#222222")
    d.text((tx, 558), "A signed message hides in the grid.", font=f_sub, fill="#222222")
    d.text((tx, 660), "svcode.org/i", font=f_url, fill="black")
    d.text((tx, 756), "scan the grid there - it verifies itself", font=f_note, fill="#666666")
    bb = d.textbbox((0, 0), "This sticker carries real Bitcoin.", font=font(44, bold=True))
    d.text(((CW - (bb[2] - bb[0])) / 2, CH - 76), "This sticker carries real Bitcoin.",
           font=font(44, bold=True), fill="black")

    out = Path(args.out) if args.out else ROOT / "stickers" / f"{args.id}-inlay.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    card.save(out, dpi=(DPI, DPI))
    code_out = out.with_name(out.stem + "-bare.png")
    code.save(code_out, dpi=(DPI, DPI))
    print(f"wrote {out} + {code_out} (QR: {qr_payload})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
