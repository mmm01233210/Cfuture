"""Script Generator — orchestrates understanding → simplification → storyboard.

Produces the canonical Arabic narration (``Script.text``) alongside its
storyboard, plus the structured understanding used for fact-checking.
"""
from __future__ import annotations

from ..config import Config
from ..models import Paper, Script, Understanding
from ..utils import get_logger
from .llm import LLM
from .simplifier import simplify
from .storyboard_generator import build_storyboard
from .understanding import understand

log = get_logger("script")


def generate(paper: Paper, llm: LLM, cfg: Config) -> tuple[Understanding, Script]:
    understanding = understand(paper, llm, cfg)
    scenes = simplify(paper, understanding, llm, cfg)
    storyboard = build_storyboard(scenes, paper, understanding)
    script_text = "\n\n".join(s.narration for s in storyboard.scenes if s.narration)
    log.info("script ready (%d scenes, %d chars)", len(storyboard.scenes), len(script_text))
    return understanding, Script(text=script_text, storyboard=storyboard)
