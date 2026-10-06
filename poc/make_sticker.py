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
    args = ap.parse_args()

    img = build_sticker(args.url, args.id, args.message)
    out = Path(args.out) if args.out else ROOT / "stickers" / f"{args.id}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, dpi=(DPI, DPI))
    print(f"wrote {out} ({W}x{H}px @ {DPI}dpi = {W_IN}x{H_IN} in)")
    print(f"QR payload: {args.url}{'&' if '?' in args.url else '?'}s={args.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
