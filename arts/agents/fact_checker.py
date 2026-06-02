"""Scientific Safety / Fact-Check Agent.

Guards against the failure modes the brief calls out: turning possibilities into
facts, inventing results, over-claiming impact, mis-attributing the work, or
forgetting to say it is research and not a finished product.

A set of deterministic checks always runs (cheap safety net). When Claude is
available it additionally verifies each claim against the abstract.
"""
from __future__ import annotations

from ..config import Config
from ..models import FactCheckIssue, FactCheckReport, Paper, Understanding
from ..utils import get_logger
from .llm import LLM

log = get_logger("factcheck")

# Hype phrasing that must not appear unless it is genuinely warranted.
_HYPE = [
    "اكتشاف تاريخي", "سيغيّر العالم", "ستغيّر العالم", "ثورة كاملة", "يقضي نهائيًا",
    "معجزة", "الأفضل في العالم", "لأول مرة في التاريخ", "سيقضي على",
]
# Wording that asserts real-world deployment.
_APPLIED = ["متوفر في السوق", "منتج جاهز", "يُستخدم الآن", "تم تطبيقه فعليًا", "صار متاحًا للجميع"]

_SYSTEM = (
    "أنت مدقّقٌ علميٌّ صارم. لديك ملخّص ورقة بحثية (abstract) وسكربت عربي مبسّط مبنيٌّ عليها. "
    "تحقّق أن السكربت لا يحرّف الورقة: كل ادّعاء مهمّ مدعومٌ من الملخّص، لا تحويل للاحتمالات "
    "إلى حقائق، لا نتائج مُختلقة، لا مبالغة في الأثر، لا نسبة خاطئة لجهةٍ أو مؤلّف، وذكرٌ أنّ "
    "العمل بحثيٌّ وليس منتجًا جاهزًا إن كان ذلك صحيحًا. "
    'أعِد JSON: {"passed": true/false, "issues":[{"severity":"error|warning|info",'
    '"claim":"المقطع","problem":"الخلل","suggestion":"التصحيح"}], "notes":"ملاحظة عامة"}. '
    "اجعل passed=false فقط عند وجود تحريفٍ جوهريٍّ (severity=error)."
)


def _deterministic_checks(paper: Paper, u: Understanding, script: str) -> list[FactCheckIssue]:
    issues: list[FactCheckIssue] = []
    for phrase in _HYPE:
        if phrase in script:
            issues.append(
                FactCheckIssue(
                    severity="warning",
                    claim=phrase,
                    problem="عبارة مبالِغة قد تتجاوز ما تدعمه الورقة.",
                    suggestion="استبدلها بصياغة محايدة مثل: قد يساعد مستقبلًا.",
                )
            )
    for phrase in _APPLIED:
        if phrase in script and u.maturity not in ("تطبيق مبكر",):
            issues.append(
                FactCheckIssue(
                    severity="warning",
                    claim=phrase,
                    problem=f"السكربت يوحي بالتطبيق الفعلي رغم أن نضج الورقة: {u.maturity}.",
                    suggestion="وضّح أنها ما زالت بحثًا وليست منتجًا جاهزًا.",
                )
            )
    if not (paper.source and paper.year and (paper.doi or paper.url)):
        issues.append(
            FactCheckIssue(
                severity="warning",
                claim="مصدر الورقة",
                problem="بيانات المصدر (المصدر/السنة/الرابط أو DOI) غير مكتملة.",
                suggestion="أضف مصدرًا واضحًا قبل النشر.",
            )
        )
    if "تنبيه" not in script and "ليست منتجًا" not in script:
        issues.append(
            FactCheckIssue(
                severity="info",
                claim="التنبيه العلمي",
                problem="لم يظهر تنبيه صريح بأن الورقة بحثية.",
                suggestion="أضف جملة توضّح أنها بحثٌ وليست منتجًا جاهزًا.",
            )
        )
    return issues


def check(paper: Paper, u: Understanding, script: str, llm: LLM, cfg: Config) -> FactCheckReport:
    issues = _deterministic_checks(paper, u, script)
    notes = "فحوصات تلقائية أساسية."

    if llm.available:
        try:
            user = f"الملخّص (abstract):\n{paper.abstract}\n\nالسكربت العربي:\n{script}"
            data = llm.complete_json(_SYSTEM, user, allow_thinking=True)
            for it in data.get("issues") or []:
                issues.append(
                    FactCheckIssue(
                        severity=str(it.get("severity", "info")).lower(),
                        claim=it.get("claim", ""),
                        problem=it.get("problem", ""),
                        suggestion=it.get("suggestion", ""),
                    )
                )
            notes = data.get("notes") or "تم التدقيق بواسطة النموذج والفحوصات التلقائية."
            log.info("fact-check via Claude (%d issues)", len(issues))
        except Exception as e:
            log.warning("LLM fact-check failed (%s) — deterministic checks only", e)
            notes = "تعذّر تدقيق النموذج؛ اعتُمدت الفحوصات التلقائية فقط."
    else:
        log.info("fact-check via deterministic checks only")

    passed = not any(i.severity == "error" for i in issues)
    return FactCheckReport(passed=passed, issues=issues, notes=notes)
