"""Thumbnail generator — a bold neon-card cover image matching the video style."""
from __future__ import annotations

from PIL import Image, ImageDraw

from ..config import Config
from ..knowledge import get_field
from ..models import Paper, Storyboard
from ..utils import ensure_fonts, get_logger
from . import visual as V

log = get_logger("thumbnail")


def render_thumbnail(paper: Paper, storyboard: Storyboard, cfg: Config, out_path: str) -> str:
    W = int(cfg.get("video.width", 1080))
    H = int(cfg.get("video.height", 1920))
    ensure_fonts(cfg)
    V.set_glyph_font_path(cfg.font_path("black"))
    fonts = V.load_fonts(cfg)
    accent = V.accent_for(cfg, paper.field)
    field = get_field(paper.field)

    img = V.background(cfg, W, H, accent, glow_cx=0.5, glow_cy=0.30).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    cx = W // 2

    V.kicker_pill(d, cx, 300, field["ar_name"], fonts["kicker"], accent)
    V.icon_chip(d, "sparkles", cx, 560, 300, accent)

    y = 820
    for ln in V.wrap(d, "ورقة بحثية", fonts["mega"], W - 150):
        V.put_center(d, cx, y, ln, fonts["mega"], V.WHITE)
        y += V.line_height(fonts["mega"], 4)
    for ln in V.wrap(d, "بشرح بسيط جدًّا", fonts["heading"], W - 150):
        V.put_center(d, cx, y, ln, fonts["heading"], accent)
        y += V.line_height(fonts["heading"], 4)

    # paper title snippet card
    title = paper.title if len(paper.title) <= 70 else paper.title[:67] + "…"
    V.rounded(d, [70, 1640, W - 70, 1820], 36, fill=(10, 15, 32, 210),
              outline=V.with_alpha(accent, 130), width=3)
    ty = 1672
    for ln in V.wrap(d, title, fonts["small"], W - 170)[:3]:
        V.put_center(d, cx, ty, ln, fonts["small"], (210, 220, 236))
        ty += V.line_height(fonts["small"], 6)

    img.save(out_path)
    log.info("thumbnail -> %s", out_path)
    return out_path
