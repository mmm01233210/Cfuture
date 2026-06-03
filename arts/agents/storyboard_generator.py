"""Storyboard Agent.

Adds the visual direction the renderer needs to each scene: an icon, a
transition and a one-line art note. Deterministic (no model call) so the look
stays consistent. Known beats get a semantic icon; any extra beats the model
invents cycle through a varied icon pool so no two neighbours look identical.
"""
from __future__ import annotations

from ..models import Paper, Scene, Storyboard, Understanding
from ..utils import get_logger

log = get_logger("storyboard")

# Per-role icon (drawn by the renderer) + transition + art note.
_VISUALS = {
    "hook": ("sparkles", "fade", "خطّاف بصري لافت مع توهّج"),
    "analogy": ("lightbulb", "pop", "تشبيه مرئي بسيط من الحياة"),
    "problem": ("question", "fade", "علامة استفهام كبيرة"),
    "authors": ("building", "slide", "بطاقة الورقة: العنوان والسنة"),
    "idea": ("lightbulb", "pop", "مصباح الفكرة"),
    "how": ("gear", "slide", "تروس وخطوات متصلة"),
    "why": ("rocket", "fade", "صاروخ يرمز للأثر المستقبلي"),
    "example": ("rocket", "fade", "مثال تطبيقي مستقبلي"),
    "key_points": ("list", "slide", "نقاط مرقّمة"),
    "caution": ("warning", "fade", "مثلث تحذير"),
    "source": ("book", "fade", "كتاب ورابط المصدر"),
}
# Cycle for unknown/extra beats so icons stay varied.
_POOL = ["sparkles", "lightbulb", "gear", "rocket", "question", "list", "book", "building"]
_TRANSITIONS = ["fade", "slide", "pop"]


def build_storyboard(scenes: list[Scene], paper: Paper, u: Understanding) -> Storyboard:
    for i, s in enumerate(scenes):
        if s.role in _VISUALS:
            icon, transition, direction = _VISUALS[s.role]
        else:
            icon = _POOL[i % len(_POOL)]
            transition = _TRANSITIONS[i % len(_TRANSITIONS)]
            direction = "مشهد سرد قصصي"
        s.icon = icon
        s.transition = transition
        s.visual_direction = direction
        if not s.highlight_words and s.on_screen_text:
            s.highlight_words = [s.on_screen_text.split(" ")[0]]
    log.info("storyboard ready (%d scenes)", len(scenes))
    return Storyboard(scenes=scenes)
