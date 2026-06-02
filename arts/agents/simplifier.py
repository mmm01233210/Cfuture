"""Arabic Simplification Agent.

Turns the structured understanding into a 9-scene, child-friendly Arabic
narration (the actual spoken/subtitle text). This is where the explanation is
made simple enough for a 10-year-old — without dumbing it down or exaggerating.

Returns a list of :class:`~arts.models.Scene` (heading, on-screen note,
narration, highlight words). Visual styling is added later by the storyboard
agent.
"""
from __future__ import annotations

from ..config import Config
from ..knowledge import get_field
from ..models import Paper, Scene, Understanding
from ..utils import get_logger
from .llm import LLM

log = get_logger("simplifier")

# Canonical scene order expected throughout the pipeline.
ROLES = ["hook", "authors", "problem", "idea", "how", "why", "key_points", "caution", "source"]

_SYSTEM = (
    "أنت كاتبُ محتوى عربيٌّ بارع، تشرح الأبحاث العلمية لطفلٍ عمره عشر سنوات بأسلوبٍ "
    "ممتعٍ ودقيق. اكتب سكربت فيديو قصير (تيك توك) عموديًّا بالعربية الفصيحة المبسّطة، "
    "مقسّمًا إلى تسعة مشاهد بالترتيب التالي بالضبط:\n"
    "hook (خطّاف جذّاب)، authors (من نشر الورقة ومتى)، problem (المشكلة مع تشبيه بسيط)، "
    "idea (الفكرة الأساسية)، how (كيف تعمل بتبسيط شديد)، why (لماذا الورقة مهمة)، "
    "key_points (أهم ٣ نقاط)، caution (تنبيه علمي أنها بحث وليست منتجًا جاهزًا إن صحّ ذلك)، "
    "source (المصدر: العنوان والسنة والمصدر).\n"
    "قواعد صارمة: لا تبالغ، لا تقل (اكتشاف تاريخي) أو (سيغيّر العالم) إلا إذا كان واضحًا جدًّا، "
    "ميّز بين (قد يساعد مستقبلًا) و(طُبِّق فعلًا)، لا تختلق أسماء جامعات أو مؤلفين، "
    "ولا تنسب الورقة لجهةٍ لم تُذكر. اجعل كل مشهدٍ من ١٠ إلى ٢٥ كلمة ليناسب ٥–٧ ثوانٍ.\n"
    'أعِد JSON بالشكل: {"scenes":[{"role":"hook","title":"عنوان قصير","on_screen_text":"سطر قصير على الشاشة",'
    '"narration":"نص الراوي","highlight_words":["كلمة"]}, ... ]} بتسعة مشاهد بالترتيب أعلاه.'
)

_HEADINGS = {
    "hook": "ورقة بحثية جديدة",
    "authors": "من نشرها؟",
    "problem": "المشكلة",
    "idea": "الفكرة الأساسية",
    "how": "كيف تعمل؟",
    "why": "لماذا تهمّنا؟",
    "key_points": "٣ نقاط مهمة",
    "caution": "تنبيه علمي",
    "source": "المصدر",
}


def _short(text: str, limit: int = 48) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


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

    narr = {
        "hook": f"هل تخيّلت كيف يتطوّر مجال {fa}؟ ورقة بحثية جديدة تأخذنا خطوةً إلى الأمام.",
        "authors": f"في عام {year}، نشر {who} ورقةً علميةً مثيرةً للاهتمام، فلنتعرّف عليها معًا.",
        "problem": f"المشكلة ببساطة: {u.problem} تخيّل أنك تركّب لعبةً جديدةً بلا كتالوج، فتحتاج طريقةً أذكى.",
        "idea": f"الفكرة الأساسية: {u.core_idea}",
        "how": f"كيف تعمل؟ {field['analogy']}",
        "why": f"لماذا هي مهمة؟ {u.importance}",
        "key_points": "أهمّ ثلاث نقاط: أولًا المشكلة، ثانيًا الفكرة الذكية، وثالثًا أنها قد تساعدنا مستقبلًا.",
        "caution": f"لكن انتبه: هذه ورقةٌ بحثية ({u.maturity})، وليست منتجًا جاهزًا في السوق بعد.",
        "source": f"المصدر: «{_short(paper.title, 60)}»، عام {year}، من {paper.source}.",
    }
    on_screen = {
        "hook": fa,
        "authors": _short(paper.title, 60),
        "problem": _short(u.problem),
        "idea": _short(u.core_idea),
        "how": _short(field["analogy"]),
        "why": _short(u.importance),
        "key_points": "المشكلة • الفكرة • الإمكانية",
        "caution": u.maturity,
        "source": f"{paper.source} — {year}",
    }
    highlights = {
        "hook": [fa],
        "authors": [str(year)],
        "problem": ["المشكلة"],
        "idea": ["الفكرة"],
        "how": [],
        "why": ["مهمة"],
        "key_points": ["مستقبلًا"],
        "caution": ["ليست", "جاهزًا"],
        "source": [paper.source],
    }
    scenes: list[Scene] = []
    for i, role in enumerate(ROLES):
        scenes.append(
            Scene(
                index=i,
                role=role,
                title=_HEADINGS[role],
                on_screen_text=on_screen[role],
                narration=narr[role],
                highlight_words=highlights[role],
            )
        )
    return scenes


def _scenes_from_llm(data: dict, paper: Paper, u: Understanding) -> list[Scene]:
    raw = data.get("scenes") or []
    scenes: list[Scene] = []
    for i, item in enumerate(raw):
        role = item.get("role") or (ROLES[i] if i < len(ROLES) else f"scene{i}")
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
        log.info("simplification via template (9 scenes)")
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
        scenes = _scenes_from_llm(data, paper, u)
        if len(scenes) < 6:  # implausible result — fall back
            raise ValueError(f"only {len(scenes)} scenes returned")
        log.info("simplification via Claude (%d scenes)", len(scenes))
        return scenes
    except Exception as e:
        log.warning("LLM simplification failed (%s) — falling back to template", e)
        return _template_scenes(paper, u)
