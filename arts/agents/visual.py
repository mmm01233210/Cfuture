"""Shared visual primitives for the modern "neon card" TikTok style.

Used by both the animated video renderer and the thumbnail so the look stays
consistent: dark gradient background, a per-field neon accent, bold Arabic
typography (native HarfBuzz shaping), rounded chips, and glow.
"""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from ..utils import ar_prepare

WHITE = (255, 255, 255)


# --------------------------------------------------------------------------- #
# Colours
# --------------------------------------------------------------------------- #
def hex_rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore


def with_alpha(c: tuple[int, int, int], a: int) -> tuple[int, int, int, int]:
    return (c[0], c[1], c[2], a)


_DEFAULT_ACCENTS = {
    "ai": "#22d3ee",
    "telecom": "#34d399",
    "quantum": "#a78bfa",
    "cybersecurity": "#fb7185",
    "robotics": "#f59e0b",
    "smart_cities": "#38bdf8",
    "emerging_tech": "#e879f9",
    "default": "#22d3ee",
}


def accent_for(cfg, field: str) -> tuple[int, int, int]:
    val = cfg.get(f"accents.{field}") or cfg.get("accents.default") or _DEFAULT_ACCENTS.get(field) or _DEFAULT_ACCENTS["default"]
    return hex_rgb(val)


def bg_colors(cfg) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    top = hex_rgb(cfg.get("theme.bg_top", "#0b1224"))
    bottom = hex_rgb(cfg.get("theme.bg_bottom", "#241844"))
    return top, bottom


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
def load_fonts(cfg) -> dict[str, ImageFont.FreeTypeFont]:
    black = cfg.font_path("black")
    bold = cfg.font_path("bold")
    return {
        "mega": ImageFont.truetype(black, 132),     # hook
        "heading": ImageFont.truetype(black, 96),
        "note": ImageFont.truetype(bold, 50),
        "cap": ImageFont.truetype(black, 58),       # active caption line
        "cap_dim": ImageFont.truetype(bold, 52),    # other caption lines
        "glyph": ImageFont.truetype(black, 132),
        "small": ImageFont.truetype(bold, 34),
        "kicker": ImageFont.truetype(black, 40),
    }


# --------------------------------------------------------------------------- #
# Text helpers (native shaping + direction)
# --------------------------------------------------------------------------- #
def measure(draw, line: str, font) -> float:
    text, direction = ar_prepare(line)
    return draw.textlength(text, font=font, direction=direction)


def put(draw, x: float, y: float, line: str, font, fill) -> None:
    text, direction = ar_prepare(line)
    draw.text((x, y), text, font=font, fill=fill, direction=direction)


def put_center(draw, cx: float, y: float, line: str, font, fill) -> int:
    w = measure(draw, line, font)
    put(draw, cx - w / 2, y, line, font, fill)
    asc, desc = font.getmetrics()
    return asc + desc


def wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = " ".join((text or "").split()).split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip()
        if measure(draw, cand, font) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def line_height(font, extra: int = 16) -> int:
    asc, desc = font.getmetrics()
    return asc + desc + extra


# --------------------------------------------------------------------------- #
# Background (dark gradient + accent glow + dot grid)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=8)
def _gradient(W: int, H: int, top: tuple, bottom: tuple) -> Image.Image:
    base = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(base)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=mix(top, bottom, y / (H - 1)))
    return base


def background(cfg, W: int, H: int, accent: tuple, glow_cx: float = 0.5, glow_cy: float = 0.28) -> Image.Image:
    top, bottom = bg_colors(cfg)
    img = _gradient(W, H, top, bottom).convert("RGBA")

    # radial accent glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gx, gy = int(W * glow_cx), int(H * glow_cy)
    for i in range(22, 0, -1):
        r = i * 46
        a = int(46 * (i / 22) ** 2)
        gd.ellipse([gx - r, gy - r, gx + r, gy + r], fill=with_alpha(accent, a))
    img = Image.alpha_composite(img, glow)

    # subtle dot grid
    dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    for yy in range(120, H - 80, 64):
        for xx in range(60, W - 40, 64):
            dd.ellipse([xx - 2, yy - 2, xx + 2, yy + 2], fill=(255, 255, 255, 12))
    return Image.alpha_composite(img, dots)


# --------------------------------------------------------------------------- #
# Chips / pills / icons
# --------------------------------------------------------------------------- #
def rounded(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def kicker_pill(draw, cx, y, text, font, accent, fg=(8, 12, 24)):
    w = measure(draw, text, font)
    pad_x, h = 30, line_height(font, 8)
    rounded(draw, [cx - w / 2 - pad_x, y, cx + w / 2 + pad_x, y + h], radius=h // 2, fill=accent)
    put(draw, cx - w / 2, y + 2, text, font, fg)
    return h


def icon_chip(draw, name, cx, cy, size, accent):
    """Rounded accent chip with a white pictogram inside."""
    half = size // 2
    # glow
    for i in range(10, 0, -1):
        r = half + i * 7
        draw.rounded_rectangle([cx - r, cy - r, cx + r, cy + r], radius=r // 2,
                               outline=with_alpha(accent, int(10 * i / 10)), width=3)
    rounded(draw, [cx - half, cy - half, cx + half, cy + half], radius=size // 4,
            fill=with_alpha(accent, 235))
    rounded(draw, [cx - half, cy - half, cx + half, cy + half], radius=size // 4,
            outline=(255, 255, 255, 60), width=3)
    _pictogram(draw, name, cx, cy, int(size * 0.66))


def _star(draw, cx, cy, r, fill):
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i - math.pi / 2
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=fill)


def _pictogram(draw, name, cx, cy, s, ink=(12, 16, 30)):
    w = WHITE
    h = s / 2
    if name == "sparkles":
        _star(draw, cx, cy, h * 0.8, w)
        _star(draw, cx - h * 0.7, cy - h * 0.55, h * 0.36, ink)
        _star(draw, cx + h * 0.7, cy + h * 0.45, h * 0.42, ink)
    elif name == "lightbulb":
        r = h * 0.62
        draw.ellipse([cx - r, cy - r - h * 0.15, cx + r, cy + r - h * 0.15], fill=w)
        draw.rectangle([cx - r * 0.5, cy + r - h * 0.2, cx + r * 0.5, cy + r + h * 0.2], fill=w)
        for a in (-1, 0, 1):
            x = cx + a * r * 1.5
            draw.line([x, cy - r * 1.9 - h * 0.15, x, cy - r * 2.4 - h * 0.15], fill=w, width=7)
    elif name == "building":
        draw.rectangle([cx - h * 0.7, cy - h * 0.8, cx + h * 0.7, cy + h * 0.8], fill=w)
        for r in range(3):
            for c in range(3):
                x = cx - h * 0.5 + c * h * 0.5
                yy = cy - h * 0.55 + r * h * 0.5
                draw.rectangle([x, yy, x + h * 0.25, yy + h * 0.25], fill=ink)
    elif name == "question":
        _glyph(draw, "؟", cx, cy, s, w)
    elif name == "warning":
        draw.polygon([(cx, cy - h * 0.8), (cx - h * 0.9, cy + h * 0.7), (cx + h * 0.9, cy + h * 0.7)], fill=w)
        _glyph(draw, "!", cx, cy + h * 0.06, int(s * 0.8), ink)
    elif name == "gear":
        r = h * 0.6
        for i in range(8):
            a = math.pi / 4 * i
            x, y = cx + r * 1.25 * math.cos(a), cy + r * 1.25 * math.sin(a)
            draw.rectangle([x - 10, y - 10, x + 10, y + 10], fill=w)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=w)
        draw.ellipse([cx - r * 0.4, cy - r * 0.4, cx + r * 0.4, cy + r * 0.4], fill=ink)
    elif name == "rocket":
        draw.polygon([(cx, cy - h * 0.9), (cx - h * 0.4, cy), (cx + h * 0.4, cy)], fill=w)
        draw.rectangle([cx - h * 0.4, cy, cx + h * 0.4, cy + h * 0.55], fill=w)
        draw.polygon([(cx - h * 0.4, cy + h * 0.55), (cx - h * 0.75, cy + h * 0.9), (cx - h * 0.08, cy + h * 0.7)], fill=w)
        draw.polygon([(cx + h * 0.4, cy + h * 0.55), (cx + h * 0.75, cy + h * 0.9), (cx + h * 0.08, cy + h * 0.7)], fill=w)
        draw.ellipse([cx - h * 0.16, cy + h * 0.05, cx + h * 0.16, cy + h * 0.37], fill=ink)
    elif name == "list":
        for i in range(3):
            y = cy - h * 0.6 + i * h * 0.6
            draw.ellipse([cx - h * 0.75, y, cx - h * 0.5, y + h * 0.25], fill=w)
            draw.line([cx - h * 0.3, y + h * 0.12, cx + h * 0.75, y + h * 0.12], fill=w, width=9)
    elif name == "book":
        draw.polygon([(cx, cy - h * 0.55), (cx - h * 0.8, cy - h * 0.35), (cx - h * 0.8, cy + h * 0.6), (cx, cy + h * 0.4)], fill=w)
        draw.polygon([(cx, cy - h * 0.55), (cx + h * 0.8, cy - h * 0.35), (cx + h * 0.8, cy + h * 0.6), (cx, cy + h * 0.4)], fill=mix(w, ink, 0.18))
        draw.line([cx, cy - h * 0.5, cx, cy + h * 0.4], fill=ink, width=4)
    else:
        _star(draw, cx, cy, h * 0.8, w)


_GLYPH_FONTS: dict[int, ImageFont.FreeTypeFont] = {}


def set_glyph_font_path(path: str):
    global _GLYPH_PATH
    _GLYPH_PATH = path


_GLYPH_PATH = None


def _glyph(draw, ch, cx, cy, size, fill):
    if not _GLYPH_PATH:
        return
    f = _GLYPH_FONTS.get(size)
    if f is None:
        f = ImageFont.truetype(_GLYPH_PATH, size)
        _GLYPH_FONTS[size] = f
    text, direction = ar_prepare(ch)
    w = draw.textlength(text, font=f, direction=direction)
    asc, desc = f.getmetrics()
    draw.text((cx - w / 2, cy - (asc + desc) / 2), text, font=f, fill=fill, direction=direction)


# --------------------------------------------------------------------------- #
# Progress bar
# --------------------------------------------------------------------------- #
def progress_bar(draw, W, y, total, idx, frac, accent):
    margin, gap, h = 70, 10, 12
    seg_w = (W - 2 * margin - (total - 1) * gap) / total
    x = margin
    for i in range(total):
        filled = 1.0 if i < idx else (frac if i == idx else 0.0)
        rounded(draw, [x, y, x + seg_w, y + h], radius=h // 2, fill=(255, 255, 255, 40))
        if filled > 0:
            rounded(draw, [x, y, x + seg_w * filled, y + h], radius=h // 2, fill=accent)
        x += seg_w + gap


# --------------------------------------------------------------------------- #
# Cinematic background helpers (photo backgrounds)
# --------------------------------------------------------------------------- #
def cover_resize(img: Image.Image, tw: int, th: int) -> Image.Image:
    """Resize + center-crop ``img`` to exactly (tw, th) without distortion."""
    img = img.convert("RGB")
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    nw, nh = max(tw, int(iw * scale + 0.5)), max(th, int(ih * scale + 0.5))
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - tw) // 2, (nh - th) // 2
    return img.crop((left, top, left + tw, top + th))


@lru_cache(maxsize=4)
def scrim(W: int, H: int, accent: tuple, base: int = 70) -> Image.Image:
    """A cinematic darkening layer: overall tint + strong top/bottom gradients."""
    layer = Image.new("RGBA", (W, H), (6, 9, 20, base))
    d = ImageDraw.Draw(layer)
    top_h, bot_h = int(H * 0.30), int(H * 0.44)
    for i in range(top_h):
        a = int(150 * (1 - i / top_h))
        d.line([(0, i), (W, i)], fill=(6, 9, 20, a))
    for i in range(bot_h):
        y = H - 1 - i
        a = int(210 * (1 - i / bot_h))
        d.line([(0, y), (W, y)], fill=(6, 9, 20, a))
    # subtle accent wash at the bottom for brand cohesion
    for i in range(int(H * 0.18)):
        y = H - 1 - i
        a = int(40 * (1 - i / (H * 0.18)))
        d.line([(0, y), (W, y)], fill=with_alpha(accent, a))
    return layer
