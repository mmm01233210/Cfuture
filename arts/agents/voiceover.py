"""Voiceover agent — synthesises calm Arabic narration per scene.

Order of preference:
  1. edge-tts  (free, natural Arabic neural voices)
  2. gTTS      (free fallback)
  3. timed silence (so the video still renders with subtitles when offline)

Returns one audio clip per scene plus its measured duration, which drives the
per-scene timing in the renderer.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from ..models import Scene
from ..utils import estimate_speech_seconds, get_logger, make_silence, media_duration

log = get_logger("voiceover")


@dataclass
class SceneAudio:
    path: str
    duration: float
    synthetic: bool  # True => silence placeholder (no real speech)


def _edge_tts(text: str, voice: str, rate: str, out_path: str) -> None:
    import edge_tts

    async def _run() -> None:
        await edge_tts.Communicate(text, voice, rate=rate).save(out_path)

    asyncio.run(_run())


def _gtts(text: str, out_path: str) -> None:
    from gtts import gTTS

    gTTS(text=text, lang="ar").save(out_path)


def _synthesize_one(text: str, out_path: str, cfg: Config) -> SceneAudio:
    provider = str(cfg.get("voiceover.provider", "edge")).lower()
    voice = cfg.get("voiceover.voice", "ar-SA-HamedNeural")
    rate = cfg.get("voiceover.rate", "-6%")
    text = " ".join((text or "").split()) or "…"

    if provider == "edge":
        try:
            _edge_tts(text, voice, rate, out_path)
            dur = media_duration(out_path)
            if dur and dur > 0.5:
                return SceneAudio(out_path, dur, False)
            raise RuntimeError("empty edge-tts output")
        except Exception as e:
            log.warning("edge-tts failed (%s) — trying gTTS", e)
            provider = "gtts"

    if provider == "gtts":
        try:
            _gtts(text, out_path)
            dur = media_duration(out_path)
            if dur and dur > 0.5:
                return SceneAudio(out_path, dur, False)
            raise RuntimeError("empty gTTS output")
        except Exception as e:
            log.warning("gTTS failed (%s) — using timed silence", e)

    # Silent fallback: duration estimated from text length.
    dur = estimate_speech_seconds(text)
    silent_path = str(Path(out_path).with_suffix(".m4a"))
    make_silence(silent_path, dur)
    return SceneAudio(silent_path, dur, True)


def synthesize(scenes: list[Scene], out_dir: str, cfg: Config) -> list[SceneAudio]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results: list[SceneAudio] = []
    for i, scene in enumerate(scenes):
        path = str(out / f"scene_{i:02d}.mp3")
        results.append(_synthesize_one(scene.narration, path, cfg))
    real = sum(1 for r in results if not r.synthetic)
    log.info("voiceover: %d/%d scenes with real speech, %.1fs total",
             real, len(results), sum(r.duration for r in results))
    return results


def fit_durations(scene_audio: list[SceneAudio], cfg: Config) -> list[float]:
    """Final per-scene on-screen durations (seconds), honouring min/max video length.

    Real speech is never sped up — we only pad. Silent placeholders are scaled to
    land the total inside [min_duration, max_duration].
    """
    min_scene = float(cfg.get("video.min_scene_seconds", 3.5))
    min_total = float(cfg.get("video.min_duration", 45))
    max_total = float(cfg.get("video.max_duration", 60))
    tail = 0.45  # breathing room after each line

    durations = [max(min_scene, a.duration + tail) for a in scene_audio]
    all_synthetic = all(a.synthetic for a in scene_audio)
    total = sum(durations)

    if all_synthetic and durations:
        target = min(max_total, max(min_total, total))
        scale = target / total
        durations = [max(min_scene, d * scale) for d in durations]
    return durations
