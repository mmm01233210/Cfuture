"""Caption builder — produces a ready-to-post TikTok caption with hashtags."""
from __future__ import annotations

from ..knowledge import hashtags_for
from ..models import Paper


def build_caption(paper: Paper) -> str:
    year = paper.year or "—"
    tags = " ".join(hashtags_for(paper.field))
    source = paper.source.replace("_", " ").title()
    lines = [
        "ورقة بحثية جديدة بشرح بسيط 👇",
        f"العنوان: {paper.title}",
        f"المصدر: {source}",
        f"السنة: {year}",
    ]
    if paper.doi:
        lines.append(f"DOI: {paper.doi}")
    lines += [
        "",
        "شرحناها بطريقة مبسطة حتى يفهمها غير المتخصص.",
        "",
        tags,
    ]
    return "\n".join(lines)
