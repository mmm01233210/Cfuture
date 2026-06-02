"""Storyboard Agent.

Takes the simplified scenes and enriches each with the visual direction the
renderer needs: an icon, a transition, a one-line art direction, and a
yellow-marker highlight word. Deterministic by design (no model call) so the
"teaching notebook" look stays consistent run to run.
"""
from __future__ import annotations

from ..models import Paper, Scene, Storyboard, Understanding
from ..utils import get_logger

log = get_logger("storyboard")

# Per-role visual recipe: icon name (drawn by the renderer), transition, art note.
_VISUALS = {
    "hook": ("sparkles", "fade", "عنوان كبير وسط الصفحة مع شرارات وخط سفلي بارز"),
    "authors": ("building", "slide", "بطاقة ورقة بحثية: العنوان والسنة داخل إطار"),
    "problem": ("question", "fade", "علامة استفهام كبيرة ودائرة حمراء حول الكلمة المهمة"),
    "idea": ("lightbulb", "pop", "مصباح مضيء وسهم يشير إلى الفكرة"),
    "how": ("gear", "slide", "تروس متصلة وأسهم تبيّن الخطوات"),
    "why": ("rocket", "fade", "صاروخ صاعد يرمز للأثر المستقبلي"),
    "key_points": ("list", "slide", "ثلاث نقاط مرقّمة بعلامات صح"),
    "caution": ("warning", "fade", "مثلث تحذير أصفر مع خط تحته"),
    "source": ("book", "fade", "كتاب ورابط المصدر في الأسفل"),
}
_DEFAULT_VISUAL = ("lightbulb", "fade", "تخطيط دفتر ملاحظات بسيط")


def build_storyboard(scenes: list[Scene], paper: Paper, u: Understanding) -> Storyboard:
    for s in scenes:
        icon, transition, direction = _VISUALS.get(s.role, _DEFAULT_VISUAL)
        s.icon = icon
        s.transition = transition
        s.visual_direction = direction
        # Ensure a heading-marker word exists for the notebook highlight.
        if not s.highlight_words and s.on_screen_text:
            s.highlight_words = [s.on_screen_text.split(" ")[0]]
    log.info("storyboard ready (%d scenes)", len(scenes))
    return Storyboard(scenes=scenes)
