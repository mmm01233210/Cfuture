"""Video Renderer — modern animated "neon card" vertical (9:16) videos.

Built for short-form (TikTok) engagement, not a static slideshow:
  * dark gradient background with a per-field neon accent glow
  * bold Arabic typography (native HarfBuzz shaping) with an accent kicker + underline
  * a real per-frame animation: content slides up + fades in, a segmented
    progress bar fills, and the narration is revealed line-by-line "karaoke"
    style with the active line lit in the accent colour
  * frames are streamed straight to ffmpeg (rawvideo) — no PNG round-trip

Each scene becomes a clip (image stream + its voiceover); clips are concatenated
into the final MP4.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from ..config import Config
from ..knowledge import get_field
from ..models import Paper, Storyboard
from ..utils import ensure_fonts, ffmpeg_exe, get_logger, run_ffmpeg
from . import backgrounds, visual as V
from .voiceover import SceneAudio, fit_durations

log = get_logger("renderer")

INTRO = 0.45  # seconds of entrance animation


def _ease_out(x: float) -> float:
    return 1 - (1 - x) ** 3


# --------------------------------------------------------------------------- #
# One scene -> one clip (frames streamed to ffmpeg)
# --------------------------------------------------------------------------- #
def _build_static(scene, idx, total, field_ar, fonts, accent, cfg, W, H):
    """Return (bg_rgba, content_rgba, base_hold_rgb, caption_lines, cap_y0, cap_lh)."""
    glow_cx = 0.5 + (0.12 if idx % 2 else -0.12)
    bg = V.background(cfg, W, H, accent, glow_cx=glow_cx, glow_cy=0.24)

    content = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(content)

    V.kicker_pill(d, W / 2, 112, field_ar, fonts["kicker"], accent)
    V.icon_chip(d, scene.icon, W // 2, 408, 240, accent)

    head_font = fonts["mega"] if scene.role == "hook" else fonts["heading"]
    hy = 600
    hlines = V.wrap(d, scene.title, head_font, W - 150)
    maxw = 0.0
    for ln in hlines:
        maxw = max(maxw, V.measure(d, ln, head_font))
        V.put_center(d, W / 2, hy, ln, head_font, V.WHITE)
        hy += V.line_height(head_font, 4)
    bar = min(180, max(110, maxw * 0.4))
    V.rounded(d, [W / 2 - bar / 2, hy + 4, W / 2 + bar / 2, hy + 16], 6, fill=accent)
    hy += 44

    if scene.on_screen_text:
        for ln in V.wrap(d, scene.on_screen_text, fonts["note"], W - 220):
            V.put_center(d, W / 2, hy, ln, fonts["note"], (205, 214, 232))
            hy += V.line_height(fonts["note"], 4)

    # caption panel + brand
    V.rounded(d, [60, 1170, W - 60, 1772], 40, fill=(10, 15, 32, 205),
              outline=V.with_alpha(accent, 130), width=3)
    V.put_center(d, W / 2, 1818, "شرح الأبحاث العلمية ببساطة", fonts["small"], (150, 160, 188))

    cap_lines = V.wrap(d, scene.narration, fonts["cap_dim"], W - 200)
    cap_lh = V.line_height(fonts["cap_dim"], 18)
    block = cap_lh * max(1, len(cap_lines))
    cap_y0 = 1170 + int(((1772 - 1170) - block) / 2) + 6

    base_hold = Image.alpha_composite(bg, content).convert("RGB")
    return bg, content, base_hold, cap_lines, cap_y0, cap_lh


def _fit_audio(src: str, dur: float, out: str) -> None:
    """Pad with trailing silence (or trim) so the track is exactly ``dur`` long."""
    run_ffmpeg([
        "-i", src, "-af", "apad", "-t", f"{dur:.3f}",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", out,
    ])


_VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")


def _read_exact(stream, n: int):
    buf = b""
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf if len(buf) == n else None


def _open_bg_decoder(bg_path: str, W: int, H: int, fps: int, dur: float):
    """ffmpeg process emitting looped, cover-cropped rgb24 frames on stdout."""
    return subprocess.Popen(
        [
            ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
            "-stream_loop", "-1", "-i", bg_path, "-t", f"{dur:.3f}",
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps}",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )


def _build_overlay(scene, field_ar, fonts, accent, cfg, W, H):
    """Caption overlay + scrim shared by image and video cinematic backgrounds."""
    scrim = V.scrim(W, H, accent, int(255 * float(cfg.get("video.bg_scrim", 0.30))))
    content = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(content)
    V.kicker_pill(d, W / 2, 108, field_ar, fonts["kicker"], accent)

    head_font = fonts["mega"] if scene.role == "hook" else fonts["heading"]
    hy = 250
    maxw = 0.0
    for ln in V.wrap(d, scene.title, head_font, W - 150):
        maxw = max(maxw, V.measure(d, ln, head_font))
        V.put_center(d, W / 2, hy, ln, head_font, V.WHITE)
        hy += V.line_height(head_font, 4)
    bar = min(200, max(110, maxw * 0.4))
    V.rounded(d, [W / 2 - bar / 2, hy + 4, W / 2 + bar / 2, hy + 16], 6, fill=accent)
    hy += 44
    if scene.on_screen_text:
        for ln in V.wrap(d, scene.on_screen_text, fonts["note"], W - 220):
            V.put_center(d, W / 2, hy, ln, fonts["note"], (222, 230, 244))
            hy += V.line_height(fonts["note"], 4)
    V.put_center(d, W / 2, 1822, "شرح الأبحاث العلمية ببساطة", fonts["small"], (210, 218, 236))

    cap_lines = V.wrap(d, scene.narration, fonts["cap_dim"], W - 150)
    cap_lh = V.line_height(fonts["cap_dim"], 18)
    block = cap_lh * max(1, len(cap_lines))
    cap_y0 = 1300 + int(((1770 - 1300) - block) / 2)

    fg_hold = Image.alpha_composite(scrim, content)
    return scrim, content, content.getchannel("A"), fg_hold, cap_lines, cap_y0, cap_lh


def _compose(base_rgba, scrim, content, content_alpha, fg_hold, intro, W, H):
    if intro < 0.999:
        off = int((1 - intro) * 70)
        a = content_alpha.point(lambda v: int(v * intro))
        c = content.copy(); c.putalpha(a)
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sh.paste(c, (0, off), c)
        return Image.alpha_composite(base_rgba, Image.alpha_composite(scrim, sh)).convert("RGB")
    return Image.alpha_composite(base_rgba, fg_hold).convert("RGB")


def _render_scene_clip(scene, idx, total, field_ar, fonts, accent, cfg,
                       W, H, fps, dur, audio_path, out_path, bg_path=None):
    cine = bool(bg_path) and Path(bg_path).exists()
    is_video = cine and bg_path.lower().endswith(_VIDEO_EXT)
    decoder = None
    big = None
    if cine:
        scrim, content, content_alpha, fg_hold, cap_lines, cap_y0, cap_lh = _build_overlay(
            scene, field_ar, fonts, accent, cfg, W, H)
        if is_video:
            decoder = _open_bg_decoder(bg_path, W, H, fps, dur)
        else:
            big = V.cover_resize(Image.open(bg_path), int(W * 1.14), int(H * 1.14))
    else:
        bg, content, base_hold, cap_lines, cap_y0, cap_lh = _build_static(
            scene, idx, total, field_ar, fonts, accent, cfg, W, H)
        content_alpha = content.getchannel("A")

    nframes = max(2, int(round(dur * fps)))
    fitted_audio = out_path[:-4] + "_a.m4a"
    _fit_audio(audio_path, dur, fitted_audio)

    proc = subprocess.Popen(
        [
            ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pixel_format", "rgb24",
            "-video_size", f"{W}x{H}", "-framerate", str(fps), "-i", "pipe:0",
            "-i", fitted_audio,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-t", f"{dur:.3f}",
            out_path,
        ],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    n_lines = max(1, len(cap_lines))
    frame_bytes = W * H * 3
    last_base = None
    try:
        for f in range(nframes):
            t = f / fps
            intro = _ease_out(min(1.0, t / INTRO))
            frac = min(1.0, t / dur)

            if cine and is_video:
                buf = _read_exact(decoder.stdout, frame_bytes)
                if buf is None:
                    base_rgba = last_base or Image.new("RGBA", (W, H), (8, 10, 22, 255))
                else:
                    base_rgba = Image.frombytes("RGB", (W, H), buf).convert("RGBA")
                    last_base = base_rgba
                frame = _compose(base_rgba, scrim, content, content_alpha, fg_hold, intro, W, H)
            elif cine:
                dx = int((big.width - W) * (0.10 + 0.7 * frac))
                dy = int((big.height - H) * (0.10 + 0.7 * frac))
                crop = big.crop((dx, dy, dx + W, dy + H)).convert("RGBA")
                frame = _compose(crop, scrim, content, content_alpha, fg_hold, intro, W, H)
            else:
                if intro < 0.999:
                    off = int((1 - intro) * 70)
                    a = content_alpha.point(lambda v: int(v * intro))
                    c = content.copy(); c.putalpha(a)
                    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sh.paste(c, (0, off), c)
                    frame = Image.alpha_composite(bg, sh).convert("RGB")
                else:
                    frame = base_hold.copy()

            fd = ImageDraw.Draw(frame)
            V.progress_bar(fd, W, 60, total, idx, frac, accent)

            active = min(n_lines - 1, int(frac * n_lines))
            yy = cap_y0
            for k, ln in enumerate(cap_lines):
                col = (210, 218, 234) if k < active else (accent if k == active else (130, 140, 165))
                V.put_center(fd, W / 2, yy, ln, fonts["cap_dim"], col)
                if k == active:
                    w = V.measure(fd, ln, fonts["cap_dim"])
                    uy = yy + V.line_height(fonts["cap_dim"], 0) - 4
                    V.rounded(fd, [W / 2 - w / 2 - 4, uy, W / 2 + w / 2 + 4, uy + 7], 4, fill=accent)
                yy += cap_lh

            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        if decoder is not None:
            try:
                decoder.stdout.close()
            except Exception:
                pass
            decoder.terminate()
    err = proc.stderr.read().decode("utf-8", "ignore")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg scene encode failed:\n{err[-1500:]}")


def render_video(storyboard: Storyboard, scene_audio: list[SceneAudio], paper: Paper,
                 cfg: Config, out_path: str, work_dir: str) -> str:
    W = int(cfg.get("video.width", 1080))
    H = int(cfg.get("video.height", 1920))
    fps = int(cfg.get("video.fps", 30))
    ensure_fonts(cfg)
    V.set_glyph_font_path(cfg.font_path("black"))
    fonts = V.load_fonts(cfg)
    accent = V.accent_for(cfg, paper.field)
    field_ar = get_field(paper.field)["ar_name"]

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    scenes = storyboard.scenes
    durations = fit_durations(scene_audio, cfg)
    bgs = backgrounds.scene_backgrounds(scenes, paper, cfg, str(work / "bg"))

    clips: list[str] = []
    for i, scene in enumerate(scenes):
        clip = str(work / f"clip_{i:02d}.mp4")
        _render_scene_clip(scene, i, len(scenes), field_ar, fonts, accent, cfg,
                           W, H, fps, durations[i], scene_audio[i].path, clip, bgs[i])
        clips.append(clip)

    concat_file = work / "concat.txt"
    concat_file.write_text("".join(f"file '{Path(c).resolve()}'\n" for c in clips), encoding="utf-8")
    run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        out_path,
    ], log)
    log.info("rendered video -> %s (%.1fs, %d scenes)", out_path, sum(durations), len(scenes))
    return out_path
