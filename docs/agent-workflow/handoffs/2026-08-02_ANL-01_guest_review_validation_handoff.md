# ANL-01 — Guest review submission input validation

**التاريخ:** 2026-08-02
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. الخلفية

بعد إغلاق MNT-01، تابعت جولة المراجعة الذاتية الحرة اللي طلبها Mohamed
("دور في CRM وMaintenance Analytics Leasing") — الميديول التالي هو
التحليلات (Analytics). أثناء مراجعة `api/router.py` لقيت الـendpoint
الوحيد في الموديول ده اللي بيستقبل كتابة من طرف **عام بالكامل بدون أي
تسجيل دخول** (`POST /analytics/reviews/submit` — استبيان رضا الضيف بعد
الخروج، محمي بتوكن JWT مؤقت 7 أيام بس، بيوصل عن طريق لينك واتساب) —
وده بالتحديد النوع من الحدود اللي CLAUDE.md §15 بيشدد عليه ("لا تثق في
أي حاجة قادمة من العميل — تحقق من كل شيء").

## 2. النتيجة

`submit_guest_review` كان بياخد `data: dict = Body(...)` خام — من غير
Pydantic schema خالص، عكس كل endpoint كتابة تاني في المشروع. أي حد ماسك
لينك الاستبيان (أو حتى بيجرّب توكن عشوائي، بما إن الـtoken مجرد JWT
موقّع بدون أي ربط إضافي بالجهاز) كان يقدر يبعت:
- `overall_rating` خارج المدى المفروض على العمود (1-5) — قيمة زي 999
  كانت هتتخزّن بصمت وتلوّث `avg_rating`/`gss_score` في كل تقرير رضا.
- عنصر `categories` ناقص `rating` — `cat_data["rating"]` كان هيرمي
  `KeyError` خام يوصل للمستخدم كـ500، مش رسالة واضحة.
- `guest_name` أطول من عمود `String(200)` — DB error خام بدل تحقق نظيف.

`overall <= 2` بيشغّل إنشاء `Activity(complaint)` تلقائي في CRM — قيمة
مفبركة زي `overall_rating=-100` كانت هتفعّل نفس الآلية دي كمان، مع
إحصائيات مالها معنى.

## 3. الإصلاح

`GuestReviewSubmitRequest`/`GuestReviewCategoryInput` schemas جديدة في
`schemas.py`:
- `overall_rating: int = Field(3, ge=1, le=5)`
- `guest_name: str = Field("ضيف", max_length=200)`
- `comment: Optional[str] = Field(None, max_length=2000)`
- `categories: list[GuestReviewCategoryInput]` — كل عنصر
  `category: str (≤30)` + `rating: int (1-5)`، الاتنين إجباريين.

الراوتر بيستخدم الـschema دلوقتي بدل `dict`، وبينادي `submit_review()`
بـ`data.model_dump()` — نفس الشكل بالظبط اللي `services.py` كان متوقعه
من الـdict الخام، فمفيش أي تغيير في طبقة الـservices خالص.

## 4. المصدر

- repo: `Resort-OS`
- branch: `claude/CX-02C-frontend-auth-bootstrap`
- commit: `0d55717`
- الملفات المتغيّرة: `backend/app/modules/analytics/schemas.py`,
  `backend/app/modules/analytics/api/router.py`,
  `backend/tests/test_api/test_analytics_http.py`

## 5. بوابة الجودة

- 4 اختبارات جديدة (`TestGuestReviewSubmitValidation`) تثبت الرفض النظيف
  422 لكل حالة: `overall_rating` خارج المدى، عنصر category ناقص rating،
  rating خارج المدى، guest_name أطول من العمود.
- الاختبارات القديمة (`test_review_insights_surfaces_category_breakdown`،
  `test_timeshare_visit_survey_token_and_submit`) عدّت زي ما هي من غير
  أي تعديل — بيانات صحيحة الشكل من قبل الإصلاح لسه بتعدي، مؤكدة إن الشكل
  المتوقع من الفرونت إند (لسه في المستودع المنفصل
  `elkheima-marketing-website`، غير موجود في هذا المستودع) متطابق تمامًا.
- `pytest tests/test_api/test_analytics_http.py -v`: 21 passed.
- `pytest tests/ -k "analytics or review or utility"`: 78 passed.
- Backend الكامل: `pytest tests/ -v` → 2191 passed, 1 failed, 42 skipped.
  الفشل الوحيد هو نفس الفشل القديم غير المرتبط الموثّق سابقًا.
- `alembic heads`: رأس واحد `88d1c505a9dc` — صفر migration.
- تحقّق مباشر داخل الحاوية الحية بعد النشر: `GuestReviewSubmitRequest
  (overall_rating=999)` رمى `ValidationError` فعليًا.

## 6. النشر

- نسخة DB قبل النشر مباشرة:
  `/var/backups/resort-os/database/resort_os_20260802_111432.dump`،
  SHA-256
  `c07404cc07489f3cd774938986db269ea5556f657a508ecf1cd4a0090979fa3a`؛
  اجتازت `pg_restore --list`.
- rollback tags: `resort-os-rollback/{backend,celery_worker,celery_beat}:pre-0d55717`
  (كانوا `b1db886`)، manifest:
  `/var/backups/resort-os/source-releases/0d55717-rollback-images.txt`.
- release: `/opt/resort-os-releases/0d55717`، current symlink محدّث.
- archive: `/var/backups/resort-os/source-releases/0d55717.tar.gz`،
  SHA-256 `ba9788b147e44c0b19f03edd5541acfb54744d576a89cab71d249fba7ca3fc21`.
- `backend`, `celery_worker`, `celery_beat` بس اتبنوا واتنشروا — `el_kheima`
  (frontend) من `b1db886` زي ما هو، مالوش تغيير في الجولة دي (الفرونت إند
  المستهلك لـendpoint ده مش في هذا المستودع أصلًا).
- 8 حاويات Running، `RestartCount=0` للثلاثة المتغيّرة، صفر severe logs.
- `https://app.elkheima.com/` → 200، `/health` → `status: ok`.

## 7. ملاحظة

الفرونت إند اللي بيستهلك الـendpoint ده فعليًا (`SurveyView.vue`) بيعيش
في مستودع `elkheima-marketing-website` المنفصل (تقسيم الموقع العام
2026-07-26) — لسه هيتراجع شكل الطلب الفعلي هناك وقت جولة الموقع القادمة
ضمن نفس المهمة الحالية ("كمل اخيرا علي الويب سايت")، لكن الـschema
الجديدة هنا مطابقة تمامًا لشكل الـdict القديم اللي كانت الشاشة القديمة
(قبل التقسيم) بترسله، فمفيش أي كسر متوقع.
