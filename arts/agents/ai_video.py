"""Animated AI video provider (image -> video).

Turns each scene's base image into a short moving clip via a real provider, so
backgrounds are genuinely animated AI footage (not just Ken Burns on a still).

Providers (pick with ``video.video_provider``; key in ``.env``):
  * replicate  — REPLICATE_API_TOKEN ; default model ``minimax/video-01``
  * fal        — FAL_KEY            ; default model ``fal-ai/kling-video/v1/standard/image-to-video``

Image-to-video keeps the subject from our generated image and is cheaper/faster
than pure text-to-video. Any failure (no key, provider error, timeout) falls
back to the still image (Ken Burns) for that scene, so rendering never breaks.

Model/field names differ per model — everything is overridable in config:
  video.video_model, video.video_image_key, video.video_input (extra params),
  video.video_duration, video.video_timeout.
"""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Optional

import requests

from ..config import Config
from ..models import Paper, Scene
from ..utils import get_logger
from .backgrounds import build_prompt

log = get_logger("ai_video")

_MOTION = "slow cinematic camera push-in, subtle parallax, gentle motion, film grain"


def _data_uri(path: str) -> str:
    ext = "jpeg" if path.lower().endswith((".jpg", ".jpeg")) else "png"
    return f"data:image/{ext};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def _download(url: str, out_path: str, timeout: int = 300) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        Path(out_path).write_bytes(r.content)
        return Path(out_path).stat().st_size > 1000
    except Exception as e:
        log.warning("video download failed (%s)", e)
        return False


# --------------------------------------------------------------------------- #
def _replicate(image_path: str, prompt: str, out_path: str, cfg: Config) -> bool:
    token = os.getenv("REPLICATE_API_TOKEN")
    if not token:
        return False
    model = cfg.get("video.video_model") or "minimax/video-01"
    image_key = cfg.get("video.video_image_key") or "first_frame_image"
    timeout = int(cfg.get("video.video_timeout", 300))
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Prefer": "wait"}
    inp = {"prompt": f"{prompt}, {_MOTION}", image_key: _data_uri(image_path)}
    inp.update(cfg.get("video.video_input") or {})

    r = requests.post(f"https://api.replicate.com/v1/models/{model}/predictions",
                      json={"input": inp}, headers=headers, timeout=120)
    if r.status_code not in (200, 201):
        log.warning("replicate create HTTP %s: %s", r.status_code, r.text[:200])
        return False
    pred = r.json()
    get_url = (pred.get("urls") or {}).get("get")
    deadline = time.time() + timeout
    while pred.get("status") in ("starting", "processing") and time.time() < deadline:
        time.sleep(3)
        pred = requests.get(get_url, headers=headers, timeout=60).json()
    if pred.get("status") != "succeeded":
        log.warning("replicate status: %s", pred.get("status"))
        return False
    out = pred.get("output")
    url = out[-1] if isinstance(out, list) and out else (out if isinstance(out, str) else None)
    return bool(url) and _download(url, out_path)


def _fal(image_path: str, prompt: str, out_path: str, cfg: Config) -> bool:
    key = os.getenv("FAL_KEY")
    if not key:
        return False
    model = cfg.get("video.video_model") or "fal-ai/kling-video/v1/standard/image-to-video"
    image_key = cfg.get("video.video_image_key") or "image_url"
    timeout = int(cfg.get("video.video_timeout", 300))
    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    inp = {"prompt": f"{prompt}, {_MOTION}", image_key: _data_uri(image_path)}
    inp.update(cfg.get("video.video_input") or {})

    r = requests.post(f"https://queue.fal.run/{model}", json=inp, headers=headers, timeout=120)
    if r.status_code not in (200, 201):
        log.warning("fal submit HTTP %s: %s", r.status_code, r.text[:200])
        return False
    job = r.json()
    status_url, response_url = job.get("status_url"), job.get("response_url")
    deadline = time.time() + timeout
    status = job.get("status")
    while status not in ("COMPLETED", "FAILED", "ERROR") and time.time() < deadline:
        time.sleep(3)
        status = requests.get(status_url, headers=headers, timeout=60).json().get("status")
    if status != "COMPLETED":
        log.warning("fal status: %s", status)
        return False
    data = requests.get(response_url, headers=headers, timeout=60).json()
    video = data.get("video") or {}
    url = video.get("url") if isinstance(video, dict) else (data.get("video_url") or None)
    return bool(url) and _download(url, out_path)


_PROVIDERS = {"replicate": _replicate, "fal": _fal}


def animate_scenes(scenes: list[Scene], paper: Paper, base_images: list[Optional[str]],
                   cfg: Config, work_dir: str) -> list[Optional[str]]:
    """Animate each base image into a clip; fall back to the image on failure."""
    provider = str(cfg.get("video.video_provider", "replicate")).lower()
    fn = _PROVIDERS.get(provider)
    out = Path(work_dir)
    out.mkdir(parents=True, exist_ok=True)
    if fn is None:
        log.warning("unknown video_provider '%s' — keeping still images", provider)
        return base_images
    if not (os.getenv("REPLICATE_API_TOKEN") or os.getenv("FAL_KEY")):
        log.warning("no video provider API key set — keeping still images (set REPLICATE_API_TOKEN or FAL_KEY)")
        return base_images

    results: list[Optional[str]] = []
    animated = 0
    for i, (scene, img) in enumerate(zip(scenes, base_images)):
        if not img:
            results.append(None)
            continue
        vid = str(out / f"clip_src_{i:02d}.mp4")
        if fn(img, build_prompt(scene, paper), vid, cfg):
            animated += 1
            results.append(vid)
        else:
            results.append(img)  # still-image fallback for this scene
    log.info("ai_video: %d/%d scenes animated via %s", animated, len(scenes), provider)
    return results
