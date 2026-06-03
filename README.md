# arabic-research-tiktok-agent

نظامٌ آليٌّ (Backend Automation) يحوِّل الأوراق البحثية الحديثة إلى **فيديوهات
TikTok عربية قصيرة، مبسّطة، ممتعة، ودقيقة** — بأسلوبٍ بصريٍّ عصريٍّ متحرّك (خلفية
داكنة متدرّجة + لون نيون لكل مجال + ترجمة "كاريوكي" + شريط تقدّم) عمودي (9:16).
الهدف: تغذية المحتوى العربي العلمي وجعل الأبحاث مفهومةً لطفلٍ عمره عشر سنوات.

> ليس موقعًا ولا لوحة تحكم — هو نظام Backend ينتج فيديوهات ويجهّزها للنشر.

---

## كيف يعمل؟ (دورة العمل)

```
Scheduler (كل ساعة)
   └─> Paper Discovery   اكتشاف أوراق حديثة من مصادر قانونية (arXiv / Semantic Scholar / Crossref / IEEE*)
   └─> Paper Scoring     تقييم كل ورقة من 100 (لا تُختار إلا إذا حصلت على ≥ 75)
   └─> Understanding     استخراج: المشكلة / الفكرة / المنهجية / النتيجة / الأهمية / الحدود / النضج
   └─> Simplification    تحويلها إلى ٩ مشاهد بالعربية المبسّطة (لطفلٍ عمره ١٠ سنوات)
   └─> Storyboard        إضافة الأيقونات والانتقالات والاتجاه البصري لكل مشهد
   └─> Fact Check        التأكّد من عدم تحريف الورقة أو المبالغة (نموذج + فحوصات تلقائية)
   └─> Voiceover         تعليق صوتي عربي (edge-tts) مع ترجمة على الشاشة
   └─> Video Render      فيديو عمودي 1080×1920، ٤٥–٦٠ ثانية
   └─> Publish/Export    حفظ الفيديو + caption جاهز (أو رفعه عبر TikTok API)
```

كل ادّعاءٍ مهمّ يُبنى على ما هو موجودٌ فعلًا في ملخّص الورقة (abstract) أو
بياناتها. النظام لا يختلق نتائج أو أسماء جهات، ويُفرّق بين «قد يساعد مستقبلًا»
و«طُبِّق فعلًا».

`*` IEEE يُستخدم للـ metadata أو Open Access فقط وعند توفّر `IEEE_API_KEY`.

---

## التشغيل السريع

```bash
# 1) المتطلبات (Python 3.11+)
pip install -r requirements.txt

# 2) (اختياري لكن مُوصى به) فعّل Claude لجودة أعلى
cp .env.example .env        # ثم ضع ANTHROPIC_API_KEY

# 3) شغّل تشغيلة واحدة كاملة
python main.py run

# أوامر أخرى
python main.py discover     # عرض الأوراق المرشّحة فقط (بدون إنتاج)
python main.py schedule     # تشغيل مستمر (كل ساعة افتراضيًا)
python main.py run --fields ai,quantum   # تجاوز المجالات لهذه التشغيلة
```

> **بدون مفتاح API**: يعمل النظام في «وضع القوالب» (template mode) وينتج فيديو
> عربيًّا متماسكًا مبنيًّا على البيانات الوصفية وقاعدة معرفة المجالات. **مع مفتاح
> نموذج** يصبح الشرح قصّة عربية عميقة مبنية على ملخّص الورقة.
>
> **اختيار النموذج** (في `config.yaml` ← `llm.provider`):
> - `anthropic` → Claude (مفتاح `ANTHROPIC_API_KEY`)
> - `gemini` → Google Gemini (مفتاح `GEMINI_API_KEY`)

### Docker

```bash
docker build -t research-tiktok .
docker run --rm -e ANTHROPIC_API_KEY=sk-... -v "$PWD/output:/app/output" research-tiktok
```

---

## مخرجات كل تشغيلة

تُنشأ مجلدٌ لكل تشغيلة:

```
output/YYYY-MM-DD-<paper-slug>/
├── final_video.mp4        # الفيديو العمودي ٩:١٦ (٤٥–٦٠ ثانية)
├── thumbnail.png          # صورة الغلاف
├── caption.txt            # وصف جاهز للنشر مع هاشتاقات حسب المجال
├── script_ar.txt          # السكربت العربي الكامل
├── storyboard.json        # المشاهد (عنوان/نص الشاشة/الراوي/أيقونة/انتقال)
├── paper_metadata.json    # بيانات الورقة + الدرجة + الفهم المنظّم
├── fact_check.json        # تقرير التدقيق العلمي
└── run.json               # ملخّص التشغيلة
```

---

## الإعدادات (`config.yaml`)

أهمّ المفاتيح (الأسرار في `.env` فقط، لا تُكتب هنا):

| المفتاح | الوصف |
|---|---|
| `fields` | المجالات النشطة: `ai, telecom, quantum, cybersecurity, robotics, smart_cities, emerging_tech` |
| `scoring.threshold` | الحد الأدنى للدرجة (افتراضي ٧٥) |
| `llm.model` | النموذج (افتراضي `claude-opus-4-8`؛ استخدم `claude-sonnet-4-6` لخفض التكلفة) |
| `voiceover.provider` / `voice` | محرّك الصوت (`edge` / `gtts` / `none`) والصوت العربي |
| `video.*` | الأبعاد، المدة (٤٥–٦٠ث)، الحركة، الموسيقى الخفيفة الاختيارية |
| `video.background` | الأسلوب البصري (انظر أدناه) |
| `publish.mode` | `export` (حفظ محليًّا) أو `tiktok_api` (رفع كمسودة) |

**الأسلوب البصري (`video.background`):**
- `ai_image` (الافتراضي): يجلب **صورة سينمائية بالذكاء الاصطناعي لكل مشهد** (عبر
  Pollinations، بلا مفتاح) ثم يطبّق حركة Ken Burns + تعتيمًا سينمائيًّا + الترجمة
  الكبيرة. **يحتاج إنترنت**؛ وعند تعذّره يتحوّل تلقائيًّا إلى `procedural`.
- `ai_video`: **خلفية فيديو AI متحرّكة فعليًّا لكل مشهد** (image→video). يحتاج مفتاح
  مزوّد في `.env`: **Replicate** (`REPLICATE_API_TOKEN`) أو **fal.ai** (`FAL_KEY`)؛
  يُضبط المزوّد/الموديل في `config.yaml` (`video.video_provider` / `video_model`).
  يتدرّج تلقائيًّا: فيديو AI ← صورة AI ← خلفية محلية.
- `procedural`: خلفيات سينمائية (تدرّج + توهّج + بوكيه) **تُولّد محليًّا بلا إنترنت**.
- `graphic`: بطاقة نيون مسطّحة (الأسلوب الأبسط).

النشر التلقائي على TikTok عبر **Content Posting API** يتطلّب `TIKTOK_ACCESS_TOKEN`
وصلاحيةً مناسبة، ويُنشر افتراضيًّا بخصوصية `SELF_ONLY` (مسودة آمنة).

---

## البنية

```
main.py                     # واجهة سطر الأوامر
arts/
├── config.py · models.py · knowledge.py · utils.py · pipeline.py · scheduler.py
└── agents/
    ├── paper_fetcher.py     · scorer.py        · understanding.py
    ├── simplifier.py        · storyboard_generator.py · script_generator.py
    ├── fact_checker.py      · voiceover.py      · video_renderer.py
    ├── thumbnail.py         · caption.py        · tiktok_uploader.py
    ├── visual.py            # أساسيات الأسلوب البصري (خلفية/ألوان/أيقونات/نصوص)
    └── llm.py               # غلاف Claude (تخزين مؤقت للموجّه + تفكير تكيّفي + احتياطي قوالب)
assets/fonts/               # خطوط Tajawal + Amiri (OFL) — تُنزَّل تلقائيًّا عند أول تشغيل
samples/sample_papers.json  # بيانات اختبار للعمل دون اتصال
```

### ملاحظات تقنية
- **النص العربي**: يُرسم بشكلٍ متّصلٍ صحيح عبر HarfBuzz/libraqm المدمج في Pillow،
  مع احتياطي `arabic-reshaper` + `python-bidi` عند غيابه.
- **الخطوط**: تُنزَّل خطوط Tajawal/Amiri (OFL) تلقائيًّا عند أول تشغيل، أو يدويًّا
  عبر `python scripts/fetch_fonts.py`.
- **ffmpeg**: يأتي جاهزًا من حزمة `imageio-ffmpeg` (لا حاجة لتثبيت ffmpeg في النظام).
- **الصوت**: عند تعذّر الاتصال بمحرّك الصوت يُولَّد صمتٌ بمدّةٍ مناسبة كي يبقى الفيديو
  قابلًا للإنتاج مع الترجمة على الشاشة.

---

## قواعد مهمة (مدمجة في التدقيق)
لا مبالغة في الأثر · لا «اكتشاف تاريخي» إلا إذا صحّ · لا نسخ حرفي لنص الورقة ·
لا scraping غير قانوني · لا أوراق بلا مصدر · لا اختلاق أسماء جامعات أو مؤلفين ·
التفريق بين «قد يساعد» و«طُبِّق».

## الاختبارات
```bash
python -m pytest -q          # أو:  python tests/test_pipeline.py
```

## الرخصة
الكود لأغراض المشروع. الخطوط ضمن `assets/fonts/` مرخّصة بـ SIL Open Font License.
البيانات في `samples/` للاختبار فقط وليست محتوًى منشورًا.
