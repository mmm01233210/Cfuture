"""Offline pipeline tests (template mode — no API key, no network, no ffmpeg).

Run with:  python -m pytest -q   (or)   python tests/test_pipeline.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arts.agents import fact_checker, paper_fetcher, scorer, script_generator
from arts.agents.caption import build_caption
from arts.agents.llm import LLM
from arts.agents.simplifier import ROLES
from arts.config import Config
from arts.utils import ar_prepare, has_arabic, slugify


def _ctx():
    cfg = Config.load()
    return cfg, LLM(cfg)


def test_discovery_has_candidates():
    cfg, _ = _ctx()
    papers = paper_fetcher.discover(cfg)
    assert papers, "expected at least the sample fixtures"


def test_selection_meets_threshold():
    cfg, llm = _ctx()
    paper, score = scorer.select_best(paper_fetcher.discover(cfg), llm, cfg)
    assert paper is not None
    assert score.total >= cfg.score_threshold
    assert score.total <= 100


def test_script_has_nine_arabic_scenes():
    cfg, llm = _ctx()
    paper, _ = scorer.select_best(paper_fetcher.discover(cfg), llm, cfg)
    understanding, script = script_generator.generate(paper, llm, cfg)
    scenes = script.storyboard.scenes
    assert len(scenes) == len(ROLES)
    assert [s.role for s in scenes] == ROLES
    assert all(s.narration for s in scenes)
    assert has_arabic(script.text)
    assert understanding.maturity


def test_factcheck_passes_in_template_mode():
    cfg, llm = _ctx()
    paper, _ = scorer.select_best(paper_fetcher.discover(cfg), llm, cfg)
    understanding, script = script_generator.generate(paper, llm, cfg)
    report = fact_checker.check(paper, understanding, script.text, llm, cfg)
    assert report.passed


def test_caption_contains_title_and_hashtag():
    cfg, llm = _ctx()
    paper, _ = scorer.select_best(paper_fetcher.discover(cfg), llm, cfg)
    cap = build_caption(paper)
    assert paper.title in cap
    assert "#" in cap


def test_text_helpers():
    assert slugify("Attention Is All You Need! 2017") == "attention-is-all-you-need-2017"
    assert slugify("ورقة عربية فقط") == "paper"
    assert has_arabic("الذكاء")
    text, direction = ar_prepare("الذكاء")
    assert direction == "rtl"
    assert ar_prepare("Hello")[1] == "ltr"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
