"""Paper Scoring Agent.

Scores each candidate out of 100 across the criteria in the brief. To keep cost
bounded, every candidate gets a cheap deterministic prescore; when Claude is
available, only the top few are re-scored by the model. A paper is produced only
if the best score reaches the configured threshold (default 75).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from ..config import Config
from ..models import Paper, Score
from ..utils import get_logger
from .llm import LLM

log = get_logger("scorer")

_MATH_MARKERS = ["\\", "theorem", "lemma", "eigen", "tensor", "∑", "∫", "∇", "manifold", "stochastic"]
_IMPACT_WORDS = ["state-of-the-art", "significant", "novel", "breakthrough", "first", "outperform", "efficient"]
_APP_WORDS = ["application", "real-world", "practical", "deploy", "clinical", "industry", "device", "system"]
_CLARITY_WORDS = ["we propose", "we present", "we introduce", "we show", "problem", "method"]

_CAPS = dict(
    recency=15, importance=15, explainability=15, real_world_application=15,
    clarity=15, short_video_fit=10, low_math_complexity=10, legal_source=5,
)


def _days_old(paper: Paper, today: date) -> Optional[int]:
    if paper.publication_date:
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                d = datetime.strptime(paper.publication_date[: len(fmt) + 2], fmt).date()
                return (today - d).days
            except ValueError:
                continue
    if paper.year:
        return (today.year - int(paper.year)) * 365
    return None


def _recency_points(days: Optional[int]) -> int:
    if days is None:
        return 8
    for limit, pts in [(30, 15), (90, 12), (180, 10), (365, 7), (730, 5)]:
        if days <= limit:
            return pts
    return 3


def heuristic_score(paper: Paper, today: Optional[date] = None) -> Score:
    today = today or date.today()
    low = (paper.abstract or "").lower()
    n = len(paper.abstract or "")

    recency = _recency_points(_days_old(paper, today))
    importance = min(15, 9 + sum(2 for w in _IMPACT_WORDS if w in low))
    math_hits = sum(1 for m in _MATH_MARKERS if m in low)
    explainability = max(6, 14 - 2 * math_hits)
    real_world = min(15, 8 + 2 * sum(1 for w in _APP_WORDS if w in low))
    clarity = min(15, 9 + 2 * sum(1 for w in _CLARITY_WORDS if w in low))
    short_fit = 9 if 400 <= n <= 1800 else (7 if n else 5)
    low_math = max(4, 10 - 2 * math_hits)
    legal = 5 if (paper.open_access or paper.source in ("arxiv",)) else (4 if paper.doi else 3)

    return Score(
        recency=recency,
        importance=importance,
        explainability=explainability,
        real_world_application=real_world,
        clarity=clarity,
        short_video_fit=short_fit,
        low_math_complexity=low_math,
        legal_source=legal,
        rationale="درجة تقديرية تلقائية اعتمادًا على الحداثة والوضوح والتطبيق والمصدر القانوني.",
    )


_SYSTEM = (
    "أنت محرّرٌ في قناة علمية عربية. قيّم صلاحية ورقة بحثية لتحويلها إلى فيديو قصير مبسّط. "
    "أعطِ درجاتٍ صحيحةً ضمن الحدود التالية: recency/15، importance/15، explainability/15، "
    "real_world_application/15، clarity/15، short_video_fit/10، low_math_complexity/10، "
    "legal_source/5. خذ بعين الاعتبار: حداثة الورقة، أهمية الموضوع، قابلية الشرح للعامة، "
    "وجود تطبيق واقعي، وضوح المشكلة والحل، قابلية تحويلها لفيديو قصير، عدم التعقيد الرياضي، "
    "وتوفّر مصدر قانوني. "
    'أعِد JSON بالمفاتيح الثمانية أعلاه (أعداد صحيحة) مع "rationale" (جملة عربية).'
)


def llm_score(paper: Paper, llm: LLM) -> Score:
    user = (
        f"العنوان: {paper.title}\n"
        f"المصدر: {paper.source} | السنة: {paper.year} | متاح مجانًا: {paper.open_access}\n"
        f"الملخّص:\n{paper.abstract}"
    )
    data = llm.complete_json(_SYSTEM, user, allow_thinking=False, max_tokens=700)
    fields = {k: int(min(_CAPS[k], max(0, round(float(data.get(k, 0)))))) for k in _CAPS}
    return Score(rationale=str(data.get("rationale", "")).strip(), **fields)


def select_best(papers: list[Paper], llm: LLM, cfg: Config) -> tuple[Optional[Paper], Optional[Score]]:
    """Return the best paper meeting the threshold, or (None, best_score)."""
    if not papers:
        return None, None
    threshold = cfg.score_threshold

    ranked = sorted(papers, key=lambda p: heuristic_score(p).total, reverse=True)
    best_paper, best_score = ranked[0], heuristic_score(ranked[0])

    # LLM re-scoring is optional (off by default) to save API calls / rate limits;
    # the heuristic already picks a strong recent paper.
    if llm.available and bool(cfg.get("scoring.use_llm", False)):
        top_k = int(cfg.get("scoring.llm_rerank_top", 3))
        refined: list[tuple[Paper, Score]] = []
        for p in ranked[:top_k]:
            try:
                refined.append((p, llm_score(p, llm)))
            except Exception as e:
                log.warning("LLM score failed for '%s' (%s)", p.title[:40], e)
                refined.append((p, heuristic_score(p)))
        best_paper, best_score = max(refined, key=lambda t: t[1].total)

    log.info("best candidate: '%s' scored %d/100 (threshold %d)",
             best_paper.title[:50], best_score.total, threshold)
    if best_score.total >= threshold:
        return best_paper, best_score
    return None, best_score
