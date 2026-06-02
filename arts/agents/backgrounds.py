"""Cinematic background provider.

Generates one striking visual per scene to sit *behind* the captions, giving the
"AI cinematic explainer" look. Default provider is Pollinations (keyless image
generation); any failure (offline, blocked, provider down) falls back to the
graphic style for that scene, so the pipeline never breaks.

The prompt for each scene is built from the field + the scene's role so the
imagery tracks the narration (hook = epic establishing shot, problem = tangled
maze, idea = glowing breakthrough, etc.). All prompts request *no text* so the
model doesn't fight our Arabic captions.
"""
from __future__ import annotations

import random
import urllib.parse
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFilter

from ..config import Config
from ..models import Paper, Scene
from ..utils import get_logger
from . import visual as V

log = get_logger("backgrounds")

# Visual vocabulary per field (English — for the image model).
_FIELD_LOOK = {
    "ai": "artificial intelligence, glowing neural network, holographic data streams, futuristic",
    "telecom": "5G and 6G wireless network, glowing signal towers over a night city, data links",
    "quantum": "quantum computer, glowing qubits, cryogenic chip, abstract physics, blue light",
    "cybersecurity": "cybersecurity, glowing digital shield and lock, streaming code, dark moody",
    "robotics": "advanced humanoid robot and robotic arm in a high-tech lab, futuristic",
    "smart_cities": "smart city at night, connected sensors and traffic, neon, aerial",
    "emerging_tech": "futuristic emerging technology, holographic interface, innovation, sleek",
}
_ROLE_LOOK = {
    "hook": "epic wide cinematic establishing shot, awe-inspiring, dramatic",
    "authors": "modern research laboratory, glowing screens, scientists at work, depth of field",
    "problem": "a complex tangled maze of glowing lines, sense of a hard problem, dramatic",
    "idea": "a single brilliant glowing lightbulb of insight, breakthrough moment",
    "how": "intricate glowing mechanism, gears and circuits of light, process",
    "why": "hopeful futuristic city skyline at sunrise, sense of impact and progress",
    "key_points": "three glowing pillars of light, clean balanced composition",
    "caution": "an early-stage lab prototype under soft warning lights, careful mood",
    "source": "an open glowing book of knowledge in a library of light",
}
_BASE_STYLE = "cinematic vertical 9:16, dramatic volumetric lighting, ultra detailed, photographic, no text, no words, no watermark"


def build_prompt(scene: Scene, paper: Paper) -> str:
    look = _FIELD_LOOK.get(paper.field, _FIELD_LOOK["emerging_tech"])
    role = _ROLE_LOOK.get(scene.role, "cinematic technology scene")
    return f"{look}, {role}, {_BASE_STYLE}"


def _pollinations_url(prompt: str, W: int, H: int, model: str, seed: int) -> str:
    q = urllib.parse.quote(prompt, safe="")
    return (f"https://image.pollinations.ai/prompt/{q}"
            f"?width={W}&height={H}&nologo=true&model={model}&seed={seed}")


def _fetch(url: str, out_path: str, timeout: int = 90) -> bool:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "arts-bg/0.1"})
        if r.status_code != 200 or not r.content:
            log.warning("background fetch HTTP %s", r.status_code)
            return False
        Path(out_path).write_bytes(r.content)
        Image.open(out_path).verify()  # ensure it's a real image
        return True
    except Exception as e:
        log.warning("background fetch failed (%s)", e)
        return False


def _provider_reachable(cfg: Config, W: int, H: int) -> bool:
    """Cheap one-shot probe so we fail fast (and don't 9x-timeout) when offline."""
    model = cfg.get("video.bg_model", "flux")
    url = _pollinations_url("a calm blue gradient", 256, 256, model, 1)
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "arts-bg/0.1"})
        return r.status_code == 200 and bool(r.content)
    except Exception:
        return False


def _procedural_image(field: str, accent: tuple, seed: int, W: int, H: int, cfg: Config) -> Image.Image:
    """Offline cinematic-style background: tinted gradient + soft bokeh + vignette."""
    rnd = random.Random(seed)
    top, bottom = V.bg_colors(cfg)
    bottom = V.mix(bottom, accent, 0.18)
    base = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(base)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=V.mix(top, bottom, y / H))

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    palette = [accent, V.mix(accent, (255, 255, 255), 0.35), (90, 120, 255), (180, 90, 230)]
    for _ in range(6):
        cx, cy = rnd.randint(0, W), rnd.randint(0, H)
        r = rnd.randint(int(W * 0.3), int(W * 0.75))
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=V.with_alpha(rnd.choice(palette), rnd.randint(30, 70)))
    base = Image.alpha_composite(base.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(140)))

    pd = ImageDraw.Draw(base)
    for _ in range(90):
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        rr = rnd.choice([1, 1, 2, 2, 3])
        pd.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(255, 255, 255, rnd.randint(20, 70)))

    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-W * 0.2, -H * 0.1, W * 1.2, H * 1.1], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(200))
    dark = Image.alpha_composite(base, Image.new("RGBA", (W, H), (4, 7, 16, 190)))
    return Image.composite(base, dark, vig).convert("RGB")


def scene_backgrounds(scenes: list[Scene], paper: Paper, cfg: Config, work_dir: str) -> list[Optional[str]]:
    """Background image path per scene.

    graphic    -> None for every scene (neon-card style)
    ai_image   -> cinematic AI photo per scene (online); procedural fallback otherwise
    procedural -> offline cinematic-style background for every scene
    """
    mode = str(cfg.get("video.background", "graphic")).lower()
    if mode == "graphic":
        return [None] * len(scenes)

    W = int(cfg.get("video.width", 1080))
    H = int(cfg.get("video.height", 1920))
    bw, bh = int(W * 1.14), int(H * 1.14)
    model = cfg.get("video.bg_model", "flux")
    accent = V.accent_for(cfg, paper.field)
    out = Path(work_dir)
    out.mkdir(parents=True, exist_ok=True)

    want_ai = mode in ("ai_image", "ai_video") and _provider_reachable(cfg, W, H)
    if mode in ("ai_image", "ai_video") and not want_ai:
        log.warning("AI image provider unreachable — using procedural cinematic backgrounds "
                    "(enable internet for real AI footage)")

    images: list[Optional[str]] = []
    fetched = 0
    for i, scene in enumerate(scenes):
        path = str(out / f"bg_{i:02d}.jpg")
        ok = False
        if want_ai:
            ok = _fetch(_pollinations_url(build_prompt(scene, paper), W, H, model, 1000 + i), path)
            fetched += int(ok)
        if not ok:
            _procedural_image(paper.field, accent, 1000 + i, bw, bh, cfg).save(path, quality=90)
        images.append(path)
    log.info("backgrounds: %d AI + %d procedural", fetched, len(scenes) - fetched)

    if mode == "ai_video":
        from . import ai_video  # lazy import (ai_video imports build_prompt from here)
        return ai_video.animate_scenes(scenes, paper, images, cfg, str(out / "clips"))
    return images
