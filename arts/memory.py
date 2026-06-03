"""Memory of already-produced papers, so the agent never repeats a paper.

Persisted as ``state/used_papers.json`` (a list of stable keys). In CI the
GitHub Actions workflow commits this file back to the repo after each run, so the
memory carries across runs.
"""
from __future__ import annotations

from .config import REPO_ROOT
from .models import Paper
from .utils import get_logger, read_json, write_json

log = get_logger("memory")

STATE_FILE = REPO_ROOT / "state" / "used_papers.json"
_MAX_KEEP = 2000


def _key(paper: Paper) -> str:
    doi = (paper.doi or "").lower().strip()
    if doi:
        return f"doi:{doi}"
    return "title:" + "".join(ch for ch in paper.title.lower() if ch.isalnum())[:90]


def load_used() -> list[str]:
    if STATE_FILE.exists():
        try:
            data = read_json(STATE_FILE)
            return [k for k in data if isinstance(k, str)]
        except Exception as e:
            log.warning("could not read memory (%s) — starting empty", e)
    return []


def is_used(paper: Paper) -> bool:
    return _key(paper) in set(load_used())


def filter_unused(papers: list[Paper]) -> list[Paper]:
    """Drop papers we've already produced; if that leaves nothing, allow repeats."""
    used = set(load_used())
    fresh = [p for p in papers if _key(p) not in used]
    if not fresh:
        log.warning("all candidates already used — allowing a repeat this run")
        return papers
    log.info("memory: %d/%d candidates are new", len(fresh), len(papers))
    return fresh


def mark_used(paper: Paper) -> None:
    used = load_used()
    k = _key(paper)
    if k in used:
        return
    used.append(k)
    used = used[-_MAX_KEEP:]
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_json(STATE_FILE, used)
    log.info("memory: recorded paper (%d total)", len(used))
