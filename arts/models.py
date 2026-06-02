"""Data models shared across the pipeline.

Plain dataclasses are used (instead of a heavier validation library) so that
every artifact serialises cleanly to JSON and stays easy to inspect by hand.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
@dataclass
class Paper:
    """A research paper discovered from a legal, authorised source."""

    title: str
    abstract: str
    source: str                       # arxiv | semantic_scholar | crossref
    url: str
    field: str                        # key from knowledge.FIELDS
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    institution: Optional[str] = None
    doi: Optional[str] = None
    publication_date: Optional[str] = None   # ISO date string
    open_access: bool = False
    license: Optional[str] = None
    pdf_url: Optional[str] = None
    paper_id: Optional[str] = None
    sample: bool = False              # True => offline test fixture, not real output
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Paper":
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
@dataclass
class Score:
    """Result of the Paper Scoring Agent (each component is 0..max)."""

    recency: int = 0                  # /15
    importance: int = 0               # /15
    explainability: int = 0           # /15
    real_world_application: int = 0   # /15
    clarity: int = 0                  # /15
    short_video_fit: int = 0          # /10
    low_math_complexity: int = 0      # /10
    legal_source: int = 0             # /5
    rationale: str = ""

    @property
    def total(self) -> int:
        return (
            self.recency
            + self.importance
            + self.explainability
            + self.real_world_application
            + self.clarity
            + self.short_video_fit
            + self.low_math_complexity
            + self.legal_source
        )


# --------------------------------------------------------------------------- #
# Understanding
# --------------------------------------------------------------------------- #
@dataclass
class Understanding:
    """Structured comprehension of the paper (source of truth for the script)."""

    problem: str = ""
    core_idea: str = ""
    method: str = ""
    key_result: str = ""
    importance: str = ""
    future_impact: str = ""
    limitations: str = ""
    maturity: str = ""                # e.g. proof-of-concept / early experiment / model / ready


# --------------------------------------------------------------------------- #
# Script + storyboard
# --------------------------------------------------------------------------- #
@dataclass
class Scene:
    index: int
    role: str                         # hook | authors | problem | idea | how | why | key_points | caution | source
    title: str
    on_screen_text: str
    narration: str
    visual_direction: str = ""
    icon: str = "lightbulb"
    transition: str = "fade"
    highlight_words: list[str] = field(default_factory=list)


@dataclass
class Storyboard:
    scenes: list[Scene] = field(default_factory=list)


@dataclass
class Script:
    """The full Arabic narration, kept alongside its storyboard."""

    text: str = ""
    storyboard: Storyboard = field(default_factory=Storyboard)


# --------------------------------------------------------------------------- #
# Fact check
# --------------------------------------------------------------------------- #
@dataclass
class FactCheckIssue:
    severity: str                     # info | warning | error
    claim: str
    problem: str
    suggestion: str = ""


@dataclass
class FactCheckReport:
    passed: bool = True
    issues: list[FactCheckIssue] = field(default_factory=list)
    notes: str = ""


# --------------------------------------------------------------------------- #
# Serialisation helpers
# --------------------------------------------------------------------------- #
def to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses (and containers) into JSON-safe data."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        # surface computed properties that are useful in artifacts
        if isinstance(obj, Score):
            out["total"] = obj.total
        return out
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj
