"""Small shared helpers: logging, filesystem, JSON, Arabic shaping, ffmpeg."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any, Optional

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import features as _pil_features

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
_CONFIGURED = False


def get_logger(name: str = "arts") -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        logging.basicConfig(
            level=os.getenv("LOG_LEVEL", "INFO").upper(),
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        _CONFIGURED = True
    return logging.getLogger(name)


# --------------------------------------------------------------------------- #
# Filesystem / JSON
# --------------------------------------------------------------------------- #
def ensure_dir(path: str | os.PathLike) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: str | os.PathLike, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_json(path: str | os.PathLike) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_text(path: str | os.PathLike, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def slugify(text: str, maxlen: int = 60) -> str:
    """ASCII slug suitable for directory names (Arabic chars are dropped)."""
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    text = re.sub(r"-{2,}", "-", text)
    return (text[:maxlen].strip("-")) or "paper"


# --------------------------------------------------------------------------- #
# Arabic text shaping (for PIL rendering)
# --------------------------------------------------------------------------- #
_reshaper = arabic_reshaper.ArabicReshaper(
    configuration={"delete_harakat": False, "support_ligatures": True}
)


def shape_ar(line: str) -> str:
    """Shape a *single* logical line of Arabic for left-to-right bitmap drawing.

    Only needed when HarfBuzz/raqm is unavailable; call per visual line.
    """
    return get_display(_reshaper.reshape(line))


def has_arabic(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" or "ݐ" <= ch <= "ݿ" for ch in text)


# True when Pillow was built with libraqm (HarfBuzz) — then PIL shapes Arabic
# itself and we should pass raw logical text with an explicit base direction.
HAS_RAQM: bool = bool(_pil_features.check("raqm"))


def ar_prepare(line: str) -> tuple[str, str]:
    """Return (text, direction) ready for ``ImageDraw.text`` / ``textlength``.

    With raqm we hand PIL the raw text and a base direction (RTL for Arabic,
    LTR otherwise) and let HarfBuzz shape + bidi-order it. Without raqm we fall
    back to manual reshaping + bidi and draw left-to-right.
    """
    if HAS_RAQM:
        return line, ("rtl" if has_arabic(line) else "ltr")
    return shape_ar(line), "ltr"


# --------------------------------------------------------------------------- #
# Fonts (OFL, fetched on demand so the repo stays binary-free)
# --------------------------------------------------------------------------- #
FONT_SOURCES = {
    "Tajawal-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/tajawal/Tajawal-Regular.ttf",
    "Tajawal-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/tajawal/Tajawal-Bold.ttf",
    "Tajawal-ExtraBold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/tajawal/Tajawal-ExtraBold.ttf",
    "Amiri-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/amiri/Amiri-Bold.ttf",
}


def ensure_fonts(cfg) -> None:
    """Download any missing configured fonts (Tajawal/Amiri, OFL) on first use."""
    import requests

    log = get_logger("fonts")
    for weight in ("regular", "bold", "black", "header"):
        try:
            path = Path(cfg.font_path(weight))
        except Exception:
            continue
        if path.exists() and path.stat().st_size > 2000:
            continue
        url = FONT_SOURCES.get(path.name)
        if not url:
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            r = requests.get(url, timeout=60, headers={"User-Agent": "arts-font-fetch/0.1"})
            r.raise_for_status()
            path.write_bytes(r.content)
            log.info("downloaded font %s (%d bytes)", path.name, len(r.content))
        except Exception as e:
            log.warning("could not fetch font %s (%s) — ensure an Arabic font is present", path.name, e)


# --------------------------------------------------------------------------- #
# Speech timing
# --------------------------------------------------------------------------- #
def estimate_speech_seconds(text: str, chars_per_second: float = 13.0) -> float:
    """Rough spoken duration for Arabic narration at a calm pace."""
    n = len(re.sub(r"\s+", " ", text or "").strip())
    return max(1.5, n / chars_per_second)


# --------------------------------------------------------------------------- #
# ffmpeg
# --------------------------------------------------------------------------- #
def ffmpeg_exe() -> str:
    """Path to an ffmpeg binary (prefers the bundled imageio-ffmpeg wheel)."""
    env = os.getenv("FFMPEG_BINARY")
    if env and Path(env).exists():
        return env
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def run_ffmpeg(args: list[str], log: Optional[logging.Logger] = None) -> str:
    """Run ffmpeg with the given args (without the leading binary)."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        msg = f"ffmpeg failed ({proc.returncode}):\n{' '.join(cmd)}\n{proc.stdout[-2000:]}"
        if log:
            log.error(msg)
        raise RuntimeError(msg)
    return proc.stdout


def media_duration(path: str | os.PathLike) -> Optional[float]:
    """Duration of an audio/video file in seconds, parsed from ffmpeg output."""
    out = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ).stdout
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
    if not m:
        return None
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def make_silence(path: str | os.PathLike, seconds: float, sample_rate: int = 44100) -> None:
    """Generate a silent stereo audio track of the given length."""
    run_ffmpeg(
        [
            "-f", "lavfi",
            "-i", f"anullsrc=channel_layout=stereo:sample_rate={sample_rate}",
            "-t", f"{seconds:.3f}",
            "-c:a", "aac", "-b:a", "128k",
            str(path),
        ]
    )
