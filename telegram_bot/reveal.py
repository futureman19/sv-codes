"""Renderer-only extraction from poc/make_genesis_001.py; NO issuer key or mint code.
Keep geometry in parity with the canonical renderer. Output stays in memory.
"""
import hashlib
import io
import math
import random
from PIL import Image, ImageDraw, ImageFilter
CANVAS = 1024

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


def render_reveal(seed_hex: str) -> bytes:
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

    output = io.BytesIO()
    img.convert("RGB").save(output, format="PNG")
    return output.getvalue()
