"""Domain knowledge base for the supported research fields.

Each field carries:
  * ``ar_name``          Arabic display name
  * ``arxiv_categories`` arXiv categories used for discovery
  * ``query``            free-text query for Semantic Scholar / Crossref
  * ``ar_description``   one simple Arabic sentence describing the field
  * ``analogy``          a child-friendly Arabic analogy used in template mode
  * ``hashtags``         field-specific Arabic/English hashtags for captions

This drives discovery, template-mode script generation and caption building, so
it is the single place to extend coverage to new domains.
"""
from __future__ import annotations

FIELDS: dict[str, dict] = {
    "ai": {
        "ar_name": "الذكاء الاصطناعي",
        "arxiv_categories": ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE"],
        "query": "artificial intelligence machine learning",
        "ar_description": "تعليمُ الآلات أن تتعلّم من الأمثلة وتتّخذ قرارات مثلما يفعل الإنسان.",
        "analogy": "تخيّل أنك تُعلّم طفلًا التفريق بين القطة والكلب بأن تُريَه صورًا كثيرة حتى يميّز بنفسه.",
        "hashtags": ["#ذكاء_اصطناعي", "#تعلم_الآلة", "#AI"],
    },
    "telecom": {
        "ar_name": "الاتصالات وشبكات الجيل الخامس والسادس",
        "arxiv_categories": ["cs.NI", "eess.SP", "cs.IT"],
        "query": "5G 6G wireless telecommunications networks",
        "ar_description": "إيجادُ طرقٍ لنقل البيانات لاسلكيًا بسرعةٍ أكبر وزحامٍ أقل.",
        "analogy": "تخيّل طريقًا سريعًا للسيارات؛ شبكات الجيل الجديد تبني مساراتٍ أكثر حتى لا يحدث ازدحام.",
        "hashtags": ["#اتصالات", "#5G", "#6G", "#شبكات"],
    },
    "quantum": {
        "ar_name": "الحوسبة الكمّية",
        "arxiv_categories": ["quant-ph"],
        "query": "quantum computing algorithms",
        "ar_description": "نوعٌ جديدٌ من الحواسيب يستفيد من قوانين الفيزياء الدقيقة لحلّ مسائل صعبة.",
        "analogy": "الحاسوب العادي يجرّب طرق المتاهة واحدًا تلو الآخر، أما الكمّي فيستكشف عدّة طرق في الوقت نفسه.",
        "hashtags": ["#حوسبة_كمية", "#الكم", "#Quantum"],
    },
    "cybersecurity": {
        "ar_name": "الأمن السيبراني",
        "arxiv_categories": ["cs.CR"],
        "query": "cybersecurity privacy attacks defense",
        "ar_description": "حمايةُ الأجهزة والبيانات من السرقة والتخريب.",
        "analogy": "تخيّل قفلًا ذكيًا لبابك يكتشف اللص قبل أن يحاول الدخول.",
        "hashtags": ["#أمن_سيبراني", "#حماية", "#Cybersecurity"],
    },
    "robotics": {
        "ar_name": "الروبوتات",
        "arxiv_categories": ["cs.RO"],
        "query": "robotics manipulation control learning",
        "ar_description": "صناعةُ آلاتٍ تتحرّك وتتعامل مع العالم من حولها.",
        "analogy": "تخيّل أنك تُعلّم يدًا آليّة أن تمسك كوبًا دون أن تكسره، تمامًا كما يتعلّم الطفل.",
        "hashtags": ["#روبوت", "#روبوتات", "#Robotics"],
    },
    "smart_cities": {
        "ar_name": "المدن الذكية",
        "arxiv_categories": ["cs.CY", "eess.SY"],
        "query": "smart city urban computing IoT sensors",
        "ar_description": "استخدامُ التقنية لجعل المدن أكثر راحةً وأقلّ ازدحامًا واستهلاكًا للطاقة.",
        "analogy": "تخيّل إشارات مرورٍ ذكيّةً تشعر بالسيارات وتفتح الطريق قبل أن يتكدّس الزحام.",
        "hashtags": ["#مدن_ذكية", "#تقنية", "#SmartCity"],
    },
    "emerging_tech": {
        "ar_name": "التقنيات الناشئة",
        "arxiv_categories": ["cs.ET", "cs.AR"],
        "query": "emerging technologies novel computing devices",
        "ar_description": "أفكارٌ تقنيّةٌ جديدةٌ قد تُغيّر طريقة استخدامنا للأجهزة مستقبلًا.",
        "analogy": "مثل أوّل هاتفٍ ذكيّ قبل أن ينتشر؛ فكرةٌ جديدةٌ تبدأ صغيرةً ثم تكبر.",
        "hashtags": ["#تقنية", "#ابتكار", "#تقنيات_ناشئة"],
    },
}

BASE_HASHTAGS = ["#علوم", "#بحث_علمي", "#تعلم", "#Research"]


def get_field(name: str) -> dict:
    """Return the field record, falling back to a generic 'emerging_tech' shape."""
    return FIELDS.get(name, FIELDS["emerging_tech"])


def all_field_keys() -> list[str]:
    return list(FIELDS.keys())


def hashtags_for(field_key: str) -> list[str]:
    field = get_field(field_key)
    # de-duplicate while preserving order
    seen: set[str] = set()
    tags: list[str] = []
    for t in field["hashtags"] + BASE_HASHTAGS:
        if t not in seen:
            seen.add(t)
            tags.append(t)
    return tags
