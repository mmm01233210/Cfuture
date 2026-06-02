"""End-to-end pipeline: discover → score → script → fact-check → render → export.

Each run produces ``output/YYYY-MM-DD-<paper-slug>/`` containing:
  paper_metadata.json · script_ar.txt · storyboard.json · fact_check.json ·
  caption.txt · thumbnail.png · final_video.mp4 · run.json
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .__init__ import __version__
from .config import Config
from .agents import paper_fetcher, scorer, script_generator, fact_checker
from .agents import voiceover, video_renderer, thumbnail, tiktok_uploader
from .agents.caption import build_caption
from .agents.llm import LLM
from .models import to_jsonable
from .utils import ensure_dir, get_logger, slugify, write_json, write_text

log = get_logger("pipeline")


def _unique_run_dir(base: Path, name: str) -> Path:
    candidate = base / name
    i = 2
    while candidate.exists():
        candidate = base / f"{name}-{i}"
        i += 1
    return ensure_dir(candidate)


def run_once(cfg: Optional[Config] = None) -> dict:
    cfg = cfg or Config.load()
    llm = LLM(cfg)

    # 1) discovery
    papers = paper_fetcher.discover(cfg)
    if not papers:
        log.warning("no papers discovered — nothing to do")
        return {"status": "no_papers"}

    # 2) scoring + selection
    paper, score = scorer.select_best(papers, llm, cfg)
    if paper is None:
        log.warning("no paper met the threshold (best=%s)", score.total if score else "n/a")
        return {"status": "below_threshold", "best_score": score.total if score else None}

    # 3) understanding + script + storyboard
    understanding, script = script_generator.generate(paper, llm, cfg)

    # 4) scientific safety / fact-check
    report = fact_checker.check(paper, understanding, script.text, llm, cfg)
    if not report.passed:
        log.warning("fact-check raised blocking issues — will render for review but NOT publish")

    # run folder
    run_name = f"{date.today().isoformat()}-{slugify(paper.title)}"
    run_dir = _unique_run_dir(ensure_dir(cfg.output_dir), run_name)
    log.info("run folder: %s", run_dir)

    # 5) voiceover (per scene)
    scene_audio = voiceover.synthesize(script.storyboard.scenes, str(run_dir / "audio"), cfg)

    # 6) render video
    final_video = str(run_dir / "final_video.mp4")
    video_renderer.render_video(script.storyboard, scene_audio, paper, cfg, final_video, str(run_dir / "work"))

    # 7) thumbnail
    thumbnail.render_thumbnail(paper, script.storyboard, cfg, str(run_dir / "thumbnail.png"))

    # 8) caption + artifacts
    caption_text = build_caption(paper)
    paper_meta = to_jsonable(paper)
    paper_meta["score"] = to_jsonable(score)
    paper_meta["understanding"] = to_jsonable(understanding)

    write_json(run_dir / "paper_metadata.json", paper_meta)
    write_text(run_dir / "script_ar.txt", script.text)
    write_json(run_dir / "storyboard.json", to_jsonable(script.storyboard))
    write_json(run_dir / "fact_check.json", to_jsonable(report))
    write_text(run_dir / "caption.txt", caption_text)

    durations = voiceover.fit_durations(scene_audio, cfg)
    run_summary = {
        "project": "arabic-research-tiktok-agent",
        "version": __version__,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "field": paper.field,
        "paper_title": paper.title,
        "source": paper.source,
        "score_total": score.total,
        "fact_check_passed": report.passed,
        "fact_check_issues": len(report.issues),
        "scenes": len(script.storyboard.scenes),
        "video_seconds": round(sum(durations), 1),
        "voice_real_scenes": sum(1 for a in scene_audio if not a.synthetic),
        "llm": "anthropic" if llm.available else "template",
        "sample_data": paper.sample,
    }
    write_json(run_dir / "run.json", run_summary)

    # 9) publish / export (only if fact-check passed)
    if report.passed:
        run_summary["publish"] = tiktok_uploader.publish(str(run_dir), cfg)
    else:
        run_summary["publish"] = {"mode": "skipped", "reason": "fact_check_failed"}
    write_json(run_dir / "run.json", run_summary)

    log.info("DONE — %s (%.1fs, %d scenes, score %d)",
             run_dir.name, run_summary["video_seconds"], run_summary["scenes"], score.total)
    return {"status": "ok", "run_dir": str(run_dir), **run_summary}
