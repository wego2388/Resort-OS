# REL-07 — Arabic PDF invoice fix, real blog content, marketing-site console-error sweep

**التاريخ:** 2026-08-04
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Claude (بتفويض مباشر من Mohamed — "انت القائد
للنهاية... اعمل ما يلزم"، خارج دورة Codex المعتادة)
**الحالة:** COMPLETE

## 1. النتيجة

Mohamed بعت سكرين شوت فاتورة أوردر حقيقية النص العربي فيها مربعات سودة
صلبة، وطلب مراجعة شاملة لشكلها. بعد التشخيص والإصلاح، وسّع الطلب لكل
صفحات الموقع التسويقي بعد ما شاف أخطاء console حقيقية (404s + Vue warning
+ InvalidStateError) على صفحة بوابة صاحب عقد التايم شير. بعد المراجعة
الكاملة، منحني تفويض واسع ("كان المشروع بتاعك") للتنظيف والنشر الكامل.

### فاتورة/إيصال PDF عربي (`backend/app/core/kernel/reports.py`)

3 باجات متسلسلة، كلها موجودة من أول ما الملف اتعمل (مش تراجع):
1. مفيش أي خط TTF متسجّل في المشروع خالص — كل الرسم كان بـ`Helvetica`
   (base-14 ReportLab، صفر glyphs عربي) رغم إن `_t()` كانت بترتّب/تعيد
   تشكيل النص صح منطقيًا.
2. `NotoSansArabic-Regular/Bold.ttf` (الخط المحلي المتاح) مالوش أي glyph
   لاتيني خالص (اتأكد بـ`fontTools.ttLib.TTFont.getBestCmap()`) — تسجيله
   لوحده كان هيصلح العربي ويمسح أي كلمة/رقم إنجليزي تمامًا.
3. `_add_footer` كانت `@staticmethod` بترسم الـtext مباشرة من غير ما
   تنادي `_t()` — تذييل الإيصال كان عربي غير متشكّل حتى بعد إصلاح البندين
   فوق.

الحل: `_split_script_runs`/`ReportBuilder._draw_mixed` يقسّموا أي سطر
لأجزاء حسب السكريبت الفعلي ويرسموا كل جزء بالخط اللي بيغطّيه (عربي/لاتيني)،
`_add_footer` بقت instance method بتنادي `_draw_mixed`. + لوجو المنتجع
الحقيقي (`app/assets/logo.png`) على الإيصال الحراري (مكنش موجود خالص)، +
تصميم أرقى (فواصل متقطّعة، تفصيل سعر تحت كل صنف، قسم إجمالي منفصل بصريًا).
الفونتات/اللوجو في `app/assets/` (مش مسار نظام) عشان `Dockerfile`'s
`COPY . /app` ينقلهم فعليًا — الصورة النهائية `python:3.11-slim` مفهاش
فونتات نظام. `dining.services.generate_receipt_pdf` اتعمله rewrite كامل.

اتأكد بـ2 رندر PDF حقيقي كامل قبل الاعتماد + `pytest -k "receipt or
report or payslip or pdf"` أخضر، وبعد النشر اتأكد فعليًا جوه container
الإنتاج: `ARABIC_FONT_AVAILABLE=True`، `logo.png` موجود فعليًا.

### مدونة حقيقية (`backend/app/modules/hub/`)

كانت skeleton كامل: `GET /hub/blog/posts` بس (query خام جوه الراوتر
نفسه، مش crud.py)، schema بيرجع `title/slug/excerpt/published_at/
views_count` بس — مفيش `body`/`cover_image` رغم إنهم موجودين في الـmodel
فعلاً، ومفيش endpoint لمقال منفرد خالص، وصفر مقالات مزروعة (`GET
/hub/blog/posts` كان بيرجع array فاضي دايمًا).

- `BlogPostItem` schema بقى فيه `cover_image`؛ `BlogPostDetail` جديد فيه
  `body`.
- `GET /hub/blog/posts/{slug}` جديد — 404 لمقال مش موجود/مسودة، بيزوّد
  `views_count` فعليًا (كان معرّف من الأول بس عمره ما اتزاد).
- الـquery المباشر جوه الراوتر اتنقل لـ`crud.list_published_blog_posts`/
  `get_published_blog_post_by_slug`/`increment_blog_post_views` — نفس نمط
  الطبقات المعتمد في المشروع.
- `app.seed._seed_blog_posts` جديد: 6 مقالات حقيقية (نص عربي منقول زي ما
  هو من `/home/wego/projects/elkheima-beach-resort` بطلب صريح من Mohamed،
  مع تحسين بسيط في الصياغة) — idempotent upsert بالـslug، نفس نمط
  `_seed_chart_of_accounts` (محتوى حقيقي آمن للتشغيل المباشر على
  production، مش demo data — `app.seed`'s الحماية الأساسية من التشغيل في
  production بتفضل سارية، الفنكشن دي بس بتتصدّر وتتشغّل منفردة).

الموقع التسويقي (`Blog.vue`/`BlogPost.vue`): كارت المقال بقى بيعرض
`cover_image` الحقيقي بدل إيموجي fallback دايمًا، صفحة المقال بقت بتنادي
الـendpoint الجديد وتعرض `post.body` كامل (`v-html`، محتوى موثوق من
فريق الموقع نفسه — مش مدخل زائر، عكس رسائل شات بوت AI الخارجية) بدل
الملخص بس.

### إصلاح شامل — الموقع التسويقي (`elkheima-marketing-website`)

سبب الأخطاء اللي Mohamed بعت سكرين شوت بيها (`/ar/timeshare/my-contract`):

- `useModulesStore`/`fetchModules` (`App.vue`) بينادي `/modules/public` —
  مفيش أي endpoint زي ده في resort-os خالص (نظام تفعيل/تعطيل الموديولات
  اتشال عمدًا من الباك إند من زمان)، وصفر consumer حقيقي لـ`hasModule()`/
  `enabledSet` في الكود كله. حُذف الملف كامل + استدعاءه.
- `useMediaSettings` بينادي `/settings/public` — نفس القصة (endpoint مش
  موجود)، `getImage`/`getText` كانوا دايمًا بيرجعوا fallback على أي حال.
  اتشال النداء، الـcomposable بقى بس بيرجع fallback مباشرة.
- `Timeshare.vue`/`Booking.vue`: `<SEOHead>` كان sibling *قبل* الـ`<div>`
  الجذر بدل ما يبقى جواه — بيخلّي الكومبوننت فيه root عنصرين (fragment)،
  وده بالظبط سبب "`[Vue warn]: Component inside <Transition> renders
  non-element root node that cannot be animated`" و`InvalidStateError`
  وقت الانتقال بين الصفحات في سكرين شوت Mohamed. 17 من الـ19 صفحة تانية
  كانوا بالفعل عاملينها صح (SEOHead جوه الـdiv) — اتصلح الاتنين ليطابقوا.
  اتأكد بفحص كل صفحات الموقع آليًا (script بيحسب عدد الـroot elements لكل
  template) — الاتنين دول كانوا الوحيدين.
- "🏖️ اطلب من مكانك" في `Beach.vue`: زرار عائم دايمًا ظاهر لأي زائر موقع
  عشوائي، بيفتح مودال طلب حقيقي (رقم شيزلونج + منتجات) بيبعت "طلب" —
  فعليًا رسالة تواصل يدوية بس (`POST /hub/contact`، زي تعليق الكود نفسه
  كان موثّق)، بدون أي تحقق حضور فعلي في المنتجع. Mohamed طلب صراحةً إنها
  تبقى "شرح للخدمة" مش استخدام مباشر من الموقع. اتشال الزرار/المودال
  الحيّين، وبقى كارت وصف بسيط بمكانهم (نفس مكوّن `SunbedOrderModal.vue`
  اتسيب موجود من غير استخدام، مش محذوف، لو حابب تفعيل حقيقي مربوط بحضور
  فعلي لاحقًا).

### اكتشاف جانبي — 147 ملف uncommitted على `/opt/resort-os`

أثناء التحضير للنشر، لقيت `/opt/resort-os` (السيرفر) فيه 147 سطر تغيير
غير محفوظ. راجعتها كلها بمقارنة منهجية:
- 100 ملف كانوا مجرد الفرق الطبيعي بين `main` (مجمّد) والفرع التشغيلي
  (أصلاً كله committed ومدفوع) — صفر خطر.
- الـ18 الباقية (عزل فروع لـ8 موديولات، أقفال تعارض دفعات، تشفير PII
  لبيانات حجوزات) كانت موثّقة في بريف من وكيل اسمه Kiro بتاريخ 2026-07-29
  (`docs/agent-workflow/PENDING_COMMIT_AND_DEPLOY_BRIEF_AR.md`). راجعتها
  سطر سطر — كانت مكتوبة بنفس نمط المشروع المعتمد بالظبط. تحقق `git log`
  أظهر إنها كانت أصلاً اتعملها commit ونشر قبل كده (commit `258c99c`،
  `git merge-base --is-ancestor 258c99c 821a718` = صح) — يعني مفيش حاجة
  ضاعت أو محتاجة إنقاذ. `/opt/resort-os` نفسه موثّق في `DEPLOYMENT.md` كـ
  "legacy source snapshot; not a deploy target" — اتسيب زي ما هو، متلمسش.

## 2. المصدر

- branch: `claude/CX-02C-frontend-auth-bootstrap`
- Resort OS commit: `5df8191` (8 commits فوق `821a718`، مدفوعة بالكامل)
- Marketing commit: `79130a6` (من المستودع المستقل، مدفوعة بالكامل)
- Resort release: `/opt/resort-os-releases/5df8191`
- Resort current: `/opt/resort-os-current -> /opt/resort-os-releases/5df8191`
- Marketing release: `/opt/elkheima-marketing-releases/79130a6`
- Marketing current: `/opt/elkheima-marketing-current -> /opt/elkheima-marketing-releases/79130a6`
- Resort archive: `/var/backups/resort-os/source-releases/5df8191.tar.gz`
- Resort archive SHA-256: `df209816d2ac9547d42cfc64c45c007a939d7d90f2a586832d30d1fde7e02963`
- Marketing archive: `/var/backups/resort-os/marketing-source-releases/79130a6.tar.gz`
- Marketing archive SHA-256: `f8e454beb95a48ac8c72ec8705c36ca50948289f2e690587a9bb629ee4fe5a9f`

## 3. بوابة الجودة

- `scripts/agent-check.sh`: passed.
- Backend `pytest tests/ -q`: passed (2300+ tests، صفر failure).
- Alembic: single head `7b4d81dc08ee` (صفر migration جديدة هذه الدفعة).
- `pnpm run type-check:all`: passed.
- `pnpm --filter el-kheima test:frontend`: 95/95 passed.
- `pnpm run build:all` (مع `VITE_PUBLIC_SITE_URL=https://elkheima.com`): passed.
- Marketing: `npm run type-check` + `npm run build` + `npm run validate:truth`: كلهم passed.
- `git diff --check`: passed.

## 4. نقطة التراجع

- pre-release DB dump: `/opt/resort-os-releases/5df8191/backups/resort_os_20260804_204745.dump`
- `pg_restore --list`: passed (1408 TOC entries).
- rollback image tags: `resort-os-rollback/{backend,celery-worker,celery-beat,el-kheima,marketing-site,nginx}:pre-5df8191`
- rollback manifest: `/var/backups/resort-os/source-releases/5df8191-rollback-images.txt`
- rollback manifest SHA-256: `8958f129c3706ce9b4cbeb0d4b93d623f2d4ec17514daf12abb8145cd6ff44bc`
- Marketing rollback tag: `resort-os-rollback/marketing-site:pre-79130a6`

لا يحتاج rollback تطبيقي متوافق إلى استعادة قاعدة البيانات (صفر migration
جديدة).

## 5. النشر

- استُبدلت الخدمات بترتيب متحكّم: `backend` → `celery_worker`+`celery_beat`
  → `el_kheima` → `nginx` (force-recreate)، بانتظار health بعد كل مرحلة.
- `marketing_site` اتبنى وانتشر منفصل (نفس دورة النشر لكن `MARKETING_SITE_CONTEXT`
  يشاور على release الماركتنج المستقل، مش جزء من بناء Resort الموحّد).
- PostgreSQL وRedis لم تُعد إنشاؤهما (دفعة تطبيقية بس).
- بعد النشر: مقالات المدونة الـ6 اتزرعت مباشرة على production عبر
  `docker exec ... python -c "from app.seed import _seed_blog_posts..."`.

## 6. قبول الإنتاج

- `elkheima.com`, `www.elkheima.com`, `app.elkheima.com`: HTTP 200.
- `/health`: `{"status":"ok", database: ok, redis: ok}`.
- 8/8 containers Running/healthy، `RestartCount=0` لكل الخدمات المستبدلة.
- Working-dir label يطابق release الجديد (`5df8191`).
- DB/Redis بقيا loopback-only (`127.0.0.1:5436`/`127.0.0.1:6381`).
- TLS SAN يشمل الدومينات الثلاثة.
- صفر أخطاء/traceback/critical/fatal في لوجات كل الخدمات المستبدلة.
- الـhealthcheck الرسمي (`resort-os-healthcheck.service`) اتشغّل يدوي
  مرتين (بعد كل نشر) — 14/14 passes الاتنين.
- تحقق حي فعلي بمتصفح Playwright حقيقي على `https://elkheima.com`: صفر
  console errors وصفر 404s على `/ar/blog`، `/ar/timeshare/my-contract`،
  `/ar/beach` — المدونة عرضت 6 مقالات حقيقية، فتح مقال عرض النص الكامل
  (5 عناوين فرعية) مش الملخص بس.
- تحقق مباشر جوه container الإنتاج: `ARABIC_FONT_AVAILABLE=True`،
  `app/assets/logo.png` موجود فعليًا.

لم يُنفذ rollback لأن كل شروط القبول نجحت.

## 7. مؤجَّل عمدًا (برّه نطاق هذه الدفعة)

- `SunbedOrderModal.vue` اتسيب موجود من غير استخدام حي على الموقع
  التسويقي — لو المالك حابب طلب حقيقي مربوط بحضور فعلي في المنتجع
  (QR/session بدل رقم شيزلونج مكتوب يدوي)، ده محتاج تصميم منفصل.
- مفيش نسخة عربي/إنجليزي منفصلة لمحتوى المدونة (`BlogPost.body` عمود
  واحد لكل حقل) — لو حابب دعم لغات فعلي لمحتوى المدونة نفسه (مش بس
  واجهة المستخدم)، محتاج migration + قرار عمارة منفصل.
- ملف `docs/agent-workflow/MKT-CMS-01_WEBSITE_CHATBOT_CONTROL_CENTER_PLAN_AR.md`
  اللي موثّق كـ"locked, not-yet-authorized" اتسيب زي ما هو — متلمسش.
