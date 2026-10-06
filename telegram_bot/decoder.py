"""Bounded, offline, display-only SV Code decoding."""
import io
import json
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'poc'))
import cv2
import numpy as np
from PIL import Image
from svcode.decode import decode_image
from svcode.codec import Decoder
from svcode.frame import unpack_frame
from svcode.envelope import Envelope
from svcode.crypto import vk_from_hex
from .reveal import render_reveal

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_DIMENSION = 8192
ISSUERS = {
    '023a6f32a0528c1b02899c3dbd28cd055fa64ca626271578da4b4261076407a11d': 'SV-GENESIS (demo)',
    '038e2cb0ea841f2975ef15d762653ea481f6bc076bcb2683d21a8dc0bc5a486538': 'Night Districts Studio (demo)',
    '031f179f4318ee0402cf66ff1f5d6eb07a8b341458b6e8c02c140a0f98cf810f0c': 'Grydbound Armory (demo)',
}
GENESIS = next(iter(ISSUERS))
MINT_LINK = 'https://svcode.org/nft/genesis/mint/'
SCAN_LINK = 'https://svcode.org/'

class DecodeFailure(ValueError):
    pass

@dataclass
class Result:
    text: str
    trusted_claim: bool = False
    reveal: bytes | None = None


def safe_text(value, limit=240):
    """Plain bounded payload text; break URL auto-linking and control characters."""
    text = str(value)
    text = ''.join(c if c.isprintable() else ' ' for c in text)
    return text.replace(':', '：').replace('.', '．').replace('@', '＠')[:limit]


def describe(raw):
    env = Envelope.parse(raw)
    # Envelope's convenience constructor substitutes current time for zero nonce.
    # Verification MUST use the exact received nonce, including zero.
    env.nonce = int.from_bytes(raw[15:19], 'big')
    issuer = next((pub for pub in ISSUERS if env.verify(vk_from_hex(pub))), None)
    lines = ['SV Code decoded', 'Signature: ' + (ISSUERS[issuer] if issuer else 'UNKNOWN / unverified — display only'),
             'Demo signature is not proof of ownership or a confirmed on-chain anchor.',
             f'Action: 0x{env.action:04X}']
    try:
        cert = json.loads(env.payload)
    except (ValueError, UnicodeError):
        cert = None
    trusted = False
    reveal = None
    if isinstance(cert, dict):
        expected = {'v': 3, 'col': 'sv-genesis', 'supply': 100, 'price': 0,
                    'endpoint': 'https://sv-mint.fly.dev', 'exp': 0}
        trusted = (issuer == GENESIS and env.action == 0xC1A1 and env.target_id == 0x47454E31
                   and cert == expected and all(type(cert[k]) is type(v) for k, v in expected.items())
                   and env.params == bytes(8) and len(env.payload) <= 227
                   and env.payload == json.dumps(expected, sort_keys=True, separators=(',', ':')).encode('utf-8'))
        if env.action == 0xC1A1:
            lines.append('Approved demo free mint token (100 total; availability not checked).' if trusted
                         else 'Mint token not approved: display only.')
            lines.append('No claims, wallet access, or spending are performed.')
        elif env.action in (0xA47C, 0x17E9):
            lines += [f'Collection: {safe_text(cert.get("col", "?"))}',
                      f'Item: {safe_text(cert.get("item", "?"))}',
                      f'Edition: {safe_text(cert.get("ed", "?"))} / {safe_text(cert.get("of", "?"))}',
                      f'Seed: {safe_text(cert.get("seed", "?"))}',
                      f'Traits: {safe_text(json.dumps(cert.get("tr", {}), ensure_ascii=True), 500)}']
            mint = cert.get('mint')
            if issuer and isinstance(mint, str) and re.fullmatch('[0-9a-f]{64}', mint) and mint != '0'*64:
                lines.append('Mint reference (not checked): https://whatsonchain.com/tx/' + mint)
            else:
                lines.append('Mint reference: pending or unverified')
            seed = cert.get('seed')
            if (issuer == GENESIS and env.target_id == 0x47454E31 and cert.get('col') == 'sv-genesis'
                    and cert.get('item') == 'genesis-blade' and isinstance(seed, str)
                    and re.fullmatch('[0-9a-f]{6}', seed)):
                reveal = render_reveal(seed)
                lines.append('Local deterministic reveal, not proof of ownership.')
    lines.append('Payload (display only): ' + safe_text(env.payload.decode('utf-8', errors='replace'), 700))
    return Result('\n'.join(lines)[:3500], trusted, reveal)


def decode_bytes(data):
    if not data or len(data) > MAX_BYTES:
        raise DecodeFailure('Image must be nonempty and at most 8 MiB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                w, h = image.size
                if (image.format not in ('PNG', 'JPEG') or getattr(image, 'n_frames', 1) != 1
                        or not 1 <= w <= MAX_DIMENSION or not 1 <= h <= MAX_DIMENSION
                        or w*h > MAX_PIXELS):
                    raise DecodeFailure('Only single-frame PNG/JPEG, up to 8192 per side / 16 MP.')
                image.verify()
        # Full pixel allocation occurs only after the header guards and validation.
        bgr = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            raise DecodeFailure('Invalid image.')
        bits = decode_image(bgr)
        seed, ctype, k, _ = unpack_frame(bits)
        if ctype != 1 or not 1 <= k <= 10 or seed != 0:
            raise DecodeFailure('Only static, single-frame envelope codes are supported.')
        raw = Decoder().feed_bits(bits)  # NEVER share fountain state between uploads.
        if raw is None:
            raise DecodeFailure('Code incomplete or corrupt. Send the original PNG as a file.')
        return describe(raw)
    except DecodeFailure:
        raise
    except Exception:
        # No exception strings: payloads and libraries can contain private data.
        raise DecodeFailure('No valid static SV Code found. Send a clear original PNG/JPEG.') from None
