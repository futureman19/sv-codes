"""verify_sticker.py — proof that a generated sticker actually works.

1. QR side: OpenCV's QR detector must read the landing URL from the print image.
2. SV side (Python decoder): crop the right grid, run the SV-0001 vision
   pipeline, parse the envelope, verify the signature (test authority).
3. SV side (JS decoder): same crop -> raw RGBA -> docs/js decoder must also
   decode it (cross-implementation check).

Usage: python verify_sticker.py stickers/demo1.png
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from svcode import crypto
from svcode.codec import Decoder
from svcode.decode import decode_image
from svcode.envelope import Envelope

ROOT = Path(__file__).resolve().parent
GOLDEN_PUB = json.loads((ROOT / "vectors" / "vectors.json").read_text())["authority_pubkey_compressed"]

passed = failed = 0
def ok(cond, name, extra=""):
    global passed, failed
    if cond: passed += 1
    else:
        failed += 1
        print("FAIL:", name, extra)

path = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "stickers" / "demo1.png")
img = Image.open(path).convert("RGB")
W, H = img.size

# --- 1. QR side
bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
det = cv2.QRCodeDetector()
data, _, _ = det.detectAndDecode(bgr)
ok(data.startswith("http") and "/j/?s=" in data, "QR decodes to landing URL", data)
print("QR payload:", data)

# --- 2. SV side, Python decoder
cell_w = (W - 100) // 2
cx = 50 + cell_w + cell_w // 2
crop = img.crop((cx - 340, 50, cx + 340, 750))
crop_bgr = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2BGR)
bits = decode_image(crop_bgr)
ok(bits is not None, "Python: anchors found in cropped SV grid")
if bits:
    dec = Decoder()
    content = dec.feed_bits(bits)
    ok(content is not None, "Python: stream solved")
    if content:
        env = Envelope.parse(content)
        pub = crypto.pubkey_hex(crypto.key_from_hex(
            json.loads((ROOT / 'vectors' / 'vectors.json').read_text())['private_key_hex']))
        ok(env.verify(crypto.vk_from_hex(pub)), "Python: envelope signature VALID (test authority)")
        print("Python decoded payload:", env.payload.decode(errors="replace")[:70], "…")

# --- 3. SV side, JS decoder
with tempfile.NamedTemporaryFile(suffix=".rgba", delete=False) as f:
    rgba_path = f.name
    f.write(np.array(crop.convert("RGBA")).tobytes())
meta = {"fixtures": {"sticker": {"file": rgba_path, "width": crop.width, "height": crop.height}}}
harness = r"""
global.SVC = require('C:/Users/futur/Desktop/sv-codes/docs/js/svc.js');
const SVDec = require('C:/Users/futur/Desktop/sv-codes/docs/js/decoder.js');
const fs = require('fs');
const m = JSON.parse(process.argv[2]);
const GOLDEN = '""" + GOLDEN_PUB + """';
const fx = m.fixtures.sticker;
const rgba = new Uint8Array(fs.readFileSync(fx.file));
const bits = SVDec.decodeImageData(rgba, fx.width, fx.height);
if (!bits) { console.log('JS: FAIL no anchors'); process.exit(1); }
const sc = new SVDec.StreamScanner(GOLDEN);
const r = sc.feedBits(bits);
if (!r) { console.log('JS: FAIL stream incomplete'); process.exit(1); }
console.log('JS: sig=' + r.sig + ' action=0x' + r.env.action.toString(16).padStart(4, '0'));
console.log('JS payload: ' + new TextDecoder().decode(r.env.payload).slice(0, 70));
process.exit(r.sig === 'valid' ? 0 : 1);
"""
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
    f.write(harness)
    harness_path = f.name
res = subprocess.run(["node", harness_path, json.dumps(meta)], capture_output=True, text=True)
print(res.stdout.strip())
ok(res.returncode == 0 and "sig=valid" in res.stdout, "JS: decodes + verifies", res.stderr[:200])

print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
