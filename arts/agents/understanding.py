"""Paper Understanding Agent — extracts a structured comprehension of a paper.

The output is the *source of truth* the script and fact-check are built on.
"""
from __future__ import annotations

from ..config import Config
from ..knowledge import get_field
from ..models import Paper, Understanding
from ..utils import get_logger
from .llm import LLM

log = get_logger("understanding")

_SYSTEM = (
    "أنت باحثٌ علميٌّ تشرح الأوراق البحثية بدقّة. مهمتك أن تقرأ بيانات الورقة وملخّصها "
    "(abstract) وتستخرج فهمًا منظّمًا لها باللغة العربية الفصيحة المبسّطة. "
    "التزم بما هو موجودٌ فعلًا في الملخّص، ولا تختلق نتائج أو أرقامًا أو أسماء جهات. "
    "ميّز بوضوح بين ما (قد يساعد مستقبلًا) وما (طُبِّق فعلًا). "
    "أعِد النتيجة على شكل JSON بالمفاتيح: problem, core_idea, method, key_result, "
    "importance, future_impact, limitations, maturity. كل قيمة جملة عربية قصيرة وواضحة. "
    "قيمة maturity واحدة من: إثبات مفهوم، نموذج أولي، تجربة أولية، محاكاة، تطبيق مبكر، بحث نظري."
)

_MATURITY_HINTS = [
    (("proof of concept", "proof-of-concept"), "إثبات مفهوم"),
    (("prototype",), "نموذج أولي"),
    (("simulation", "simulated", "in silico"), "محاكاة"),
    (("preliminary", "early-stage", "early stage", "first step"), "تجربة أولية"),
    (("deployed", "in production", "real-world deployment", "commercial"), "تطبيق مبكر"),
    (("theoretical", "we prove", "proof of"), "بحث نظري"),
]


def _detect_maturity(abstract: str) -> str:
    low = (abstract or "").lower()
    for keys, label in _MATURITY_HINTS:
        if any(k in low for k in keys):
            return label
    return "تجربة أولية"


def _template_understanding(paper: Paper) -> Understanding:
    field = get_field(paper.field)
    fa = field["ar_name"]
    return Understanding(
        problem=f"كيف نطوّر مجال {fa} ونحلّ تحدّيًا مهمًا فيه بطريقةٍ أفضل من السابق.",
        core_idea=field["ar_description"],
        method="اعتمد الباحثون على التجربة والقياس والمقارنة مع الطرق السابقة لاختبار فكرتهم.",
        key_result="حصلوا على نتائج أوّليّة واعدة مقارنةً بما كان متاحًا من قبل.",
        importance=f"قد تفتح الباب مستقبلًا لتحسين {fa} وجعله أكثر فائدة في حياتنا.",
        future_impact=f"ربّما تساعد لاحقًا في تطبيقاتٍ عمليّةٍ ضمن مجال {fa}.",
        limitations="ما زالت في مراحلها الأولى وتحتاج إلى مزيدٍ من الاختبار قبل الاستخدام الواسع.",
        maturity=_detect_maturity(paper.abstract),
    )


def understand(paper: Paper, llm: LLM, cfg: Config) -> Understanding:
    if not llm.available:
        log.info("understanding via template")
        return _template_understanding(paper)
    try:
        user = (
            f"العنوان: {paper.title}\n"
            f"المجال: {get_field(paper.field)['ar_name']}\n"
            f"السنة: {paper.year or 'غير معروفة'}\n"
            f"الجهة: {paper.institution or 'غير مذكورة'}\n"
            f"الملخّص (abstract):\n{paper.abstract}"
        )
        data = llm.complete_json(_SYSTEM, user, allow_thinking=True)
        u = Understanding(
            problem=data.get("problem", ""),
            core_idea=data.get("core_idea", ""),
            method=data.get("method", ""),
            key_result=data.get("key_result", ""),
            importance=data.get("importance", ""),
            future_impact=data.get("future_impact", ""),
            limitations=data.get("limitations", ""),
            maturity=data.get("maturity") or _detect_maturity(paper.abstract),
        )
        log.info("understanding via Claude (maturity=%s)", u.maturity)
        return u
    except Exception as e:
        log.warning("LLM understanding failed (%s) — falling back to template", e)
        return _template_understanding(paper)
