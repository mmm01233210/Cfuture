"""Arabic Simplification Agent.

Turns the structured understanding into a vivid, story-driven Arabic narration —
a sequence of short, punchy beats (10–14 scenes) that build curiosity the way a
good science explainer does: a strong hook, an everyday analogy, the problem, who
did it, the idea, how it works, why it matters, a real-world example, the key
points, an honest scientific caution, and the source.

Each beat stays short (fits one on-screen caption), so together they form a
richer, longer, engaging video. Visual styling is added by the storyboard agent.
The vivid storytelling quality comes from Claude (set ANTHROPIC_API_KEY); the
template fallback produces a coherent, honest — if plainer — version offline.
"""
from __future__ import annotations

from ..config import Config
from ..knowledge import get_field
from ..models import Paper, Scene, Understanding
from ..utils import get_logger
from .llm import LLM

log = get_logger("simplifier")

# Canonical beat order used in template mode (the LLM may return 10–14 beats).
ROLES = ["hook", "analogy", "problem", "authors", "idea", "how",
         "why", "example", "key_points", "caution", "source"]

_SYSTEM = (
    "أنت كاتبُ محتوى عربيٌّ بارع، تحوّل الأوراق البحثية إلى قصّةٍ علميةٍ قصيرةٍ مشوّقة "
    "يفهمها طفلٌ عمره عشر سنوات. اكتب سكربت فيديو عمودي (تيك توك) بالعربية الفصيحة "
    "المبسّطة، بأسلوب السرد القصصي: جُملٌ قصيرةٌ متتابعة، خطّافٌ قويٌّ في البداية، "
    "تشبيهٌ من الحياة اليومية يجعل الفكرة محسوسة، ثم بناءٌ تدريجيٌّ للفضول.\n"
    "قسّم السكربت إلى ١٠ حتى ١٤ مشهدًا قصيرًا، كل مشهد جملةٌ أو جملتان (٨ إلى ٢٤ كلمة) "
    "تناسب ٤–٧ ثوانٍ. اتبع هذا القوس: hook (خطّاف)، analogy (تشبيه حياتي)، problem (المشكلة)، "
    "authors (من نشرها ومتى)، idea (الفكرة الأساسية)، how (كيف تعمل بتبسيط)، "
    "why (لماذا تهمّ القارئ)، example (مثال/تطبيق واقعي محتمل)، key_points (خلاصة سريعة)، "
    "caution (تنبيه علمي صادق)، source (المصدر). يمكنك إضافة مشهدٍ أو مشهدين للتشبيه أو "
    "الشرح لإثراء القصّة.\n"
    "قواعد صارمة: لا تبالغ، لا تقل (اكتشاف تاريخي) أو (سيغيّر العالم) إلا إذا كان واضحًا جدًّا، "
    "ميّز بين (قد يساعد مستقبلًا) و(طُبِّق فعلًا)، لا تختلق أسماء جامعات أو مؤلفين أو أرقامًا، "
    "ولا تنسب الورقة لجهةٍ لم تُذكر، ولا تنسخ نص الورقة حرفيًّا.\n"
    'أعِد JSON فقط بالشكل: {"scenes":[{"role":"hook","title":"عنوان قصير على الشاشة",'
    '"on_screen_text":"سطر داعم قصير","narration":"نص الراوي","highlight_words":["كلمة"]}, ...]} '
    "بعشرة إلى أربعة عشر مشهدًا."
)

_HEADINGS = {
    "hook": "تخيّل معي",
    "analogy": "شبّهها بهذا",
    "problem": "المشكلة",
    "authors": "من نشرها؟",
    "idea": "الفكرة",
    "how": "كيف تعمل؟",
    "why": "لماذا تهمّك؟",
    "example": "مثال واقعي",
    "key_points": "باختصار",
    "caution": "تنبيه علمي",
    "source": "المصدر",
}


def _short(text: str, limit: int = 46) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _authors_phrase(paper: Paper) -> str:
    inst = ""
    if paper.institution and not paper.sample:
        inst = f" من {paper.institution}"
    return "فريقٌ من الباحثين" + inst


def _template_scenes(paper: Paper, u: Understanding) -> list[Scene]:
    field = get_field(paper.field)
    fa = field["ar_name"]
    year = paper.year or "السنوات الأخيرة"
    who = _authors_phrase(paper)
    title = _short(paper.title, 55)

    narr = {
        "hook": f"توقّف لحظة… في مجال {fa} ظهرت فكرةٌ جديدةٌ قد تغيّر أشياء حولنا. تعال نفهمها ببساطة.",
        "analogy": field["analogy"],
        "problem": f"المشكلة باختصار: {u.problem}",
        "authors": f"في عام {year} نشر {who} ورقةً علميةً تحاول حلّ هذا التحدّي تحديدًا.",
        "idea": f"الفكرة الأساسية ببساطة: {u.core_idea}",
        "how": "كيف تعمل؟ بدل الطريقة التقليدية، جرّبوا أسلوبًا يتعلّم ويصحّح نفسه خطوةً خطوة.",
        "why": f"لماذا يهمّك هذا؟ لأنه {u.importance}",
        "example": f"قد نلمس أثره مستقبلًا في تطبيقاتٍ تخدم حياتنا اليومية داخل مجال {fa}.",
        "key_points": "باختصار: مشكلةٌ صعبة، فكرةٌ ذكية، ونتيجةٌ أوّليّةٌ واعدةٌ تفتح بابًا جديدًا للبحث.",
        "caution": f"لكن بصدق: هذه ورقةٌ بحثية ({u.maturity})، خطوةٌ في طريقٍ طويل وليست منتجًا جاهزًا اليوم.",
        "source": f"المصدر: «{title}»، عام {year}، من {paper.source}. ابحث عنها إن أردت التعمّق.",
    }
    on_screen = {
        "hook": fa,
        "analogy": "تشبيه من الحياة",
        "problem": _short(u.problem),
        "authors": title,
        "idea": _short(u.core_idea),
        "how": "أسلوبٌ يتعلّم",
        "why": _short(u.importance),
        "example": fa,
        "key_points": "مشكلة • فكرة • نتيجة",
        "caution": u.maturity,
        "source": f"{paper.source} — {year}",
    }
    highlights = {
        "hook": [fa],
        "analogy": [],
        "problem": ["المشكلة"],
        "authors": [str(year)],
        "idea": ["الفكرة"],
        "how": [],
        "why": ["يهمّك"],
        "example": ["مستقبلًا"],
        "key_points": ["واعدة"],
        "caution": ["ليست", "جاهزًا"],
        "source": [paper.source],
    }
    return [
        Scene(
            index=i,
            role=role,
            title=_HEADINGS[role],
            on_screen_text=on_screen[role],
            narration=narr[role],
            highlight_words=highlights[role],
        )
        for i, role in enumerate(ROLES)
    ]


def _scenes_from_llm(data: dict) -> list[Scene]:
    raw = data.get("scenes") or []
    scenes: list[Scene] = []
    for i, item in enumerate(raw):
        role = item.get("role") or (ROLES[i] if i < len(ROLES) else f"beat{i}")
        scenes.append(
            Scene(
                index=i,
                role=role,
                title=item.get("title") or _HEADINGS.get(role, ""),
                on_screen_text=item.get("on_screen_text", ""),
                narration=item.get("narration", ""),
                highlight_words=[w for w in (item.get("highlight_words") or []) if isinstance(w, str)][:2],
            )
        )
    return scenes


def simplify(paper: Paper, u: Understanding, llm: LLM, cfg: Config) -> list[Scene]:
    if not llm.available:
        log.info("simplification via template (%d beats)", len(ROLES))
        return _template_scenes(paper, u)
    try:
        field = get_field(paper.field)
        user = (
            f"العنوان: {paper.title}\n"
            f"المجال: {field['ar_name']}\n"
            f"السنة: {paper.year or 'غير معروفة'}\n"
            f"الجهة: {paper.institution or 'غير مذكورة'}\n"
            f"النضج: {u.maturity}\n\n"
            f"الفهم المنظّم للورقة:\n"
            f"- المشكلة: {u.problem}\n- الفكرة: {u.core_idea}\n- المنهجية: {u.method}\n"
            f"- أهم نتيجة: {u.key_result}\n- الأهمية: {u.importance}\n"
            f"- الأثر المستقبلي: {u.future_impact}\n- الحدود: {u.limitations}\n"
        )
        data = llm.complete_json(_SYSTEM, user, allow_thinking=True)
        scenes = _scenes_from_llm(data)
        if len(scenes) < 7:  # implausible result — fall back
            raise ValueError(f"only {len(scenes)} scenes returned")
        log.info("simplification via Claude (%d beats)", len(scenes))
        return scenes
    except Exception as e:
        log.warning("LLM simplification failed (%s) — falling back to template", e)
        return _template_scenes(paper, u)
