# REL-06 — HR/Admin/Timeshare audit batch (23 commits) — direct deploy

**التاريخ:** 2026-08-03
**المالك:** Mohamed
**المنفذ:** Claude (بتفويض مباشر من Mohamed، خارج دورة مراجعة Codex المعتادة —
Mohamed طلب صراحة: "ظبط كل الشغل ده بطريقتك" ثم "ارفع علي الفي بي اس")
**الحالة:** COMPLETE

## 1. لماذا

بعد إغلاق مراجعة الأمن/الأدمن الأولى في نفس الجلسة (فك قفل حساب، سجل
تدقيق، حذف نظام إشعارات ميت، جلسات إدارية)، طلب Mohamed مراجعة إضافية
لموديول التايم شير تحديدًا (عقود/أقساط/استيراد/بوابة الضيف). طلعت فجوتين
حقيقيتين، ووافق عليهم. بعدها سأل عن الخطوة التالية، فاقترحت رفع الـ23
commit المتراكمة محليًا من الجلسات السابقة بدل فتح موديول جديد — وافق
وطلب التنفيذ والنشر مباشرة.

## 2. النطاق (23 commit، `5b02010..821a718`)

- **مالي**: `vat_percentage`/`service_charge_percentage` كانا بيتقروا من
  env var ثابت بس بغض النظر عن قيمة الإعدادات الفعلية — بقوا DB-driven
  حقيقي في `dining`/`beach`/`finance`.
- **HR**: بحث/فلترة حقيقية (كانت client-side على أول 100 سجل بس)، تعديل
  بيانات موظف + تغيير حالة (إجازة/إيقاف/إنهاء مع تعطيل حساب المستخدم
  المرتبط)، تحميل رواتب Excel/PDF وقسائم فردية، ملف موظف موحّد. إصلاح
  IDOR حقيقي: `GET /hr/employees/{id}` مكانش فيه أي فحص فرع.
- **أدمن (super_admin)**: فك قفل حساب بعد محاولات دخول فاشلة، إعادة ضبط
  2FA لموظف فقد جهازه، إدارة جلسات (`RefreshToken` families) مستخدم تاني
  (عرض/إنهاء — step-up)، فلترة سجل التدقيق بمدى تاريخ + اسم الفاعل، حذف
  نظام Notification كامل (model/CRUD/service/router) كان مبني بالكامل من
  غير أي مستهلك في الفرونت إند أو منتِج في أي موديول تاني.
- **تايم شير**: إدارة وحدات فعلية (CRUD)، قائمة انتظار حقيقية (تحويل
  تلقائي لأول عميل منتظر لما وحدة تفضى)، تذكيرات واتساب (صيانة مستحقة،
  انتهاء عقد)، نسبة إشغال في اللوحة، بوابة صاحب عقد ذاتية كاملة (OTP عبر
  واتساب، عرض العقد/الدفعات، تحميل PDF)، إصلاح باج حقيقي في البوابة
  (كانت بتعمل logout للعميل عند أي خطأ عابر بدل الاحتفاظ بالتوكن).
  **جولة تانية بعد طلب Mohamed مراجعة أعمق**: تنبيهات واتساب حقيقية في
  الاتجاهين لطلبات الزيارة وتذاكر الدعم (مكانتش موجودة خالص — العميل
  والموظف مالهومش أي طريقة يعرفوا فيه حاجة جديدة)، مؤشرين في لوحة خدمة
  العملاء (`pending_visit_requests`/`open_support_tickets`) + badge على
  التابات، زرار توليد مستحقات صيانة يدوي (endpoint كان موجود بدون UI).
- **دايننج** (كانت موجودة في الفرع من قبل الجلسة دي، اتضمّت للدفعة):
  هوية ضيف + طلب ذاتي عابر للمنافذ + ملاحظات/إضافات لكل صنف، منيو ضيف
  4 لغات (ar/en/ru/it)، idempotency لطلب الضيف، بث خريطة الطاولات الحي،
  فئة تسالي جديدة للكافيه.

## 3. Migrations (4، صفر تعارض، head واحد `7b4d81dc08ee`)

- `a7c3f0e9d5b2` — dining i18n columns + item sort_order
- `f1e6c8b4a3d7` — dining order item name_ar snapshot
- `7e5e126360d5` — guest_name/guest_phone على guest_sessions + dining_orders
- `7b4d81dc08ee` — timeshare visit_requests + support_tickets tables

كلها additive (أعمدة/جداول جديدة)، صفر حذف عمود، صفر تعارض مع أي migration
سابقة.

## 4. باج أمني حقيقي اتصلح وقت preflight النشر (مش نظري)

`docker compose run --rm --no-deps backend python -c "from app.main import app"`
فشل بـ`ValidationError: TIMESHARE_PORTAL_TOKEN_SECRET ضعيف أو افتراضي` —
الـfail-closed validator ده (`app/core/config.py::_validate_token_signing_secrets`،
مُضاف في commit `4ee29a2` بنفس الدفعة) بيرفض يشتغل في production لو
المفتاح فاضي. `.env.prod` الفعلي على السيرفر مكانش فيه المفتاح ده خالص —
الميزة (بوابة صاحب العقد) اتبنت بعد آخر نشر (`5b02010`) فمكانش موجود في
نسخة `.env.prod` القديمة. لو الـvalidator ده مكانش موجود، كان أي حد يعرف
الكود العام (المستودع على GitHub) يقدر يوقّع توكن بوابة عميل تايم شير
مزوّر بمفتاح فاضي/معروف، ويشوف بيانات أي عميل تايم شير ويقدّم طلبات
باسمه من غير أي تحقق OTP حقيقي.

**الإصلاح**: ولّدت `secrets.token_urlsafe(48)` حقيقي وأضفته لـ
`/opt/resort-os-releases/821a718/backend/.env.prod` مباشرة على السيرفر
(append، من غير أي طباعة للمفتاح في أي مكان). أعدت تشغيل preflight checks
— عدّت نظيفة. المفتاح ده هيتوارث تلقائيًا لأي إصدار جاي (كل إصدار جديد
بينسخ `.env.prod` من الإصدار السابق).

## 5. بوابة الجودة (محلي، قبل أي push)

- `bash scripts/agent-check.sh` — كل الفحوصات القابلة للقراءة عدّت.
- `pytest tests/ -v` (backend كامل) → صفر رجوع؛ الفشل الوحيد هو تست معروف
  مسبقًا غير مرتبط (`test_timeshare_maintenance.py::
  TestFreezeUnfreezeInteraction::test_paying_maintenance_unfreezes_when_no_other_overdue`،
  اتأكد بـ`git stash` إنه بيفشل على الأساس النظيف كمان — pre-existing).
- `alembic heads` → رأس واحد.
- `pnpm run type-check:all` (كل الـworkspace) → نظيف.
- `pnpm --filter el-kheima test:frontend` (i18n validation + vitest) →
  95 اختبار Vitest عدّوا + i18n parity (6143 مفتاح ar/en، صفر ناقص).
- `pnpm run build:all` → بنى نظيف (`VITE_PUBLIC_SITE_URL=https://elkheima.com`
  محلي بس للتحقق، الإنتاج بيستخدم قيمته الحقيقية من `.env.prod`/build arg).
- **14 اختبار جديد** لتنبيهات بوابة التايم شير (الاتجاهين) + مؤشرات
  cs-summary — كلهم عدّوا.
- **6 اختبار جديد** لإدارة الجلسات الإدارية (صلاحية، عزل بيانات بين
  المستخدمين، step-up مطلوب، نجاح الإنهاء، 404).
- **8 اختبار جديد** لفك القفل/إعادة ضبط 2FA.

## 6. النشر (VPS `191.218.161.133`، Compose project `resort-os-prod`)

- `git push origin claude/CX-02C-frontend-auth-bootstrap` — fast-forward
  نظيف، صفر تعارض (`5b02010` سلف مباشر لـ`821a718`).
- Archive: `/var/backups/resort-os/source-releases/821a718.tar.gz`،
  SHA-256 `542cdaa35f7dfb6ae1dd6da68c825d65954da2606a57783ff177c479f35a4411`
  — تحقّق checksum مطابق بين المصدر المحلي والسيرفر قبل الاستخراج.
- Release: `/opt/resort-os-releases/821a718`، `.env.prod` منسوخ من
  `5b02010` + `TIMESHARE_PORTAL_TOKEN_SECRET` الجديد (راجع §4)، تحقّق
  `validate_prod_env.py` نجح.
- Rollback tags: `resort-os-rollback/{backend,celery-worker,celery-beat,
  el-kheima,marketing-site,nginx}:pre-821a718` (كانوا `5b02010`)، manifest
  كامل: `/var/backups/resort-os/source-releases/821a718-rollback-images.txt`.
- DB backup قبل أي تغيير:
  `/opt/resort-os-releases/5b02010/backups/resort_os_20260803_232155.dump`،
  SHA-256 `e9eff9a27f3d81403de4f7589d385a4c5bdaebb141b19d297fe27e8852f1969b`،
  اجتاز `pg_restore --list` (1373 TOC entries، تحقّق فعلي داخل حاوية DB).
- Build: `backend`, `celery_worker`, `celery_beat`, `el_kheima`,
  `marketing_site` (سياق `1371975` بدون تغيير مصدر، جزء من أمر البناء
  الموحّد فقط) — الخمسة بُنوا بنجاح.
- Preflight: import check ✅ (بعد إصلاح §4)، `alembic heads` ✅ (رأس
  واحد يطابق المحلي)، `alembic upgrade head` ✅ (4 migrations اتطبّقوا
  بالترتيب الصحيح، صفر خطأ).
- استبدال متحكم فيه بالترتيب: `backend` → healthy (6 محاولات، ~18 ثانية)
  → `celery_worker`+`celery_beat` → healthy (2 محاولة) → `el_kheima`+
  `marketing_site` → running/healthy → `nginx --force-recreate`.
- `/opt/resort-os-current` symlink محدّث لـ`821a718` (كان لسه واقف على
  `5b02010` من نشرة سابقة).

## 7. التحقق بعد النشر

- 8/8 حاويات Running/healthy، `RestartCount=0` للستة المستبدلة.
- `docker inspect ... working_dir` يطابق `/opt/resort-os-releases/821a718`.
- `https://elkheima.com/`، `https://www.elkheima.com/`،
  `https://app.elkheima.com/` → 200 كلهم من برّه الـVPS.
- `https://app.elkheima.com/health` → `status: ok`، DB latency 1.1ms،
  Redis latency 1.2ms.
- `alembic current` (داخل الحاوية الحية) → `7b4d81dc08ee (head)`.
- عدد صفوف `users`/`branches` بعد النشر مطابق لما قبله (2/1) — صفر فقد
  بيانات.
- TLS SAN لسه شامل النطاقات الثلاثة.
- DB/Redis لسه loopback-only (`127.0.0.1:5436`/`127.0.0.1:6381`).
- صفر traceback/critical/fatal/emergency في لوجات backend/nginx خلال
  نافذة النشر.
- `resort-os-healthcheck.service` (البوابة الرسمية الآلية) اتشغّل يدويًا
  بعد النشر مباشرة → `RESORT_HEALTHCHECK_OK passes=14`.

## 8. المخاطر المتبقية / ملاحظات

- هذه الدفعة اتنفّذت ونُشرت بواسطتي مباشرة بتفويض صريح من Mohamed، خارج
  دورة مراجعة Codex المعتادة المذكورة في `AGENTS.md`. لو Mohamed حابب
  مراجعة Codex لاحقة على أي جزء منها (خصوصًا الأجزاء المالية أو الجلسات
  الإدارية)، الكود والاختبارات موجودة كاملة في الـ23 commit المذكورة.
- `MARKETING_SITE_CONTEXT` والـ`marketing_site` نفسها متغيّرتش المصدر —
  بُنيت فقط كجزء من أمر البناء الموحّد، صفر تغيير فعلي في محتواها.
- توثيق تايم شير الإضافي (استيراد Excel، تقارير، عقود/أقساط تفصيليًا) لسه
  محتاج مراجعة أعمق منفصلة لو Mohamed حابب يكمل — الجولة دي غطت بس
  الفجوتين اللي طلعوا (تنبيهات بوابة الضيف + زرار التوليد اليدوي).
