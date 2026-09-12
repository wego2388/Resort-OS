# Production Handoff — POS Tablet/PWA + Post-payment Guest Rating

**التاريخ:** 2026-09-12
**المنفذ والمراجع:** Codex
**الحالة:** منشور ومتحقق على VPS الإنتاج `31.97.193.77`

## المصدر المنشور

- Resort OS commit:
  `76602f093f3f5b3dd28f77d4767ba7273de6b150` على branch
  `feat/tablet-unified-pos-pwa`، ومدفوع إلى `origin`.
- Marketing commit:
  `e369bb418f1d8b91afc1a19bd3f946bac43d52e7` على branch
  `feat/guest-review-after-payment`، ومدفوع إلى `origin`.
- Resort active link:
  `/opt/resort-os-current -> /opt/resort-os-releases/76602f093f3f5b3dd28f77d4767ba7273de6b150`.
- Marketing active link:
  `/opt/elkheima-marketing-current -> /opt/elkheima-marketing-releases/e369bb418f1d8b91afc1a19bd3f946bac43d52e7`.

التغيير الوظيفي والملفات الأساسية موثقان في التسليم المحلي السابق:
`docs/agent-workflow/handoffs/2026-09-12_pos-tablet-guest-rating_codex_handoff.md`.

## نقطة الرجوع قبل النشر

- Resort archive:
  `/var/backups/resort-os/source-releases/76602f093f3f5b3dd28f77d4767ba7273de6b150.tar.gz`.
- Resort SHA-256:
  `312b8975fc3450c6c09d92ff1973145b0e88db4eccab5f2b195c451a26c11537`.
- Marketing archive:
  `/var/backups/resort-os/marketing-source-releases/e369bb418f1d8b91afc1a19bd3f946bac43d52e7.tar.gz`.
- Marketing SHA-256:
  `e35c97ef8e9b92f1b2b2a71befb97a6cfc9c892d2a2c28fdd45c10ba965a4a80`.
- Fresh DB dump:
  `/opt/resort-os-releases/76602f093f3f5b3dd28f77d4767ba7273de6b150/backups/resort_os_20260912_095324.dump`
  (780839 bytes)، وتحقق `pg_restore --list` منه بنجاح.
- Rollback image manifest:
  `/var/backups/resort-os/source-releases/76602f093f3f5b3dd28f77d4767ba7273de6b150-rollback-images.txt`.
- الـResort السابق:
  `/opt/resort-os-releases/5a6036cfae8ee7104d548d020f9b50c07a095bcb`.
- الـMarketing السابق:
  `/opt/elkheima-marketing-releases/961bb773d9431c243b384e5ae02596c38c418322`.

حُفظت tags قبل البناء لخدمات Backend/Celery وEl Kheima وMarketing وNginx
تحت `resort-os-rollback/*:pre-76602f093f3f5b3dd28f77d4767ba7273de6b150`.
صورة Owner القديمة كانت running-only وغير قابلة لإعادة الوسم محليًا، لذلك
سُجل ID الخاص بها في manifest ولم يُبنَ أو يُستبدل Owner في هذا الإصدار؛
الحاوية بقيت كما هي وRestartCount=0.

## قاعدة البيانات والتوافق

- نُفذت migration واحدة للأمام:
  `0ccdcfb7c5c9 -> d2e4f6a8c0b1`.
- القراءة المباشرة من `alembic_version` و`alembic current` أكدتا
  `d2e4f6a8c0b1 (head)`.
- تحقق وجود الفهرسين الفريدين الجزئيين:
  `uq_guest_review_dining_order` و`uq_guest_review_guest_session`.
- التغيير إضافي: عمودان nullable وFKs/indexes جديدة. رجوع التطبيق المتوافق
  لا يحتاج restore لقاعدة البيانات؛ لا يُستخدم الـdump إلا إذا ثبت فساد
  بيانات مستقل.
- لم تُشغّل أي seed أو import، ولم تُنشأ طلبات أو تقييمات تجريبية.

## البناء والاستبدال

- `validate_prod_env.py`: PASS.
- Compose domain config: PASS.
- بُنيت فقط صور `backend` و`el_kheima` و`marketing_site` من الإصدارين
  المحددين.
- preflight import أعاد `El Kheima Beach`، وAlembic head داخل الصورة صحيح.
- الاستبدال تم بالتسلسل:
  Backend → Celery worker/beat → El Kheima/Marketing → Nginx.
- PostgreSQL وRedis وOwner لم تُعد إنشاؤها.
- Nginx `nginx -t`: PASS.

## أدلة الاختبار قبل النشر

- `bash scripts/agent-check.sh`: PASS؛ 3035 Backend tests collected؛
  Alembic single head؛ Compose dev/prod config PASS.
- Backend الكامل: وصل 100% بـexit 0 دون failures.
- Staff: i18n 6705/6705؛ Vitest 108/108؛ Playwright mock 19/19؛
  type-check وPWA production build PASS.
- Owner: Playwright 12/12؛ type-check وproduction build PASS.
- Marketing: public-truth وtype-check وproduction build PASS؛
  `npm audit --omit=dev` = صفر vulnerabilities.

## قبول الإنتاج

- التسع حاويات Running؛ الحاويات ذات healthchecks أصبحت healthy؛ كل
  RestartCount=0.
- Backend وCelery worker وCelery beat لها نفس image ID
  `sha256:e9ca4b19c382216b6bc37b8ed9195fcd7fd501909b36ef7af34ea8d27bc69008`
  ونفس revision الكامل `76602f093f3f5b3dd28f77d4767ba7273de6b150`.
- `elkheima.com` و`www.elkheima.com` و`app.elkheima.com` و
  `owner.elkheima.com`: HTTPS 200 من خارج الخادم.
- `/health`: `status=ok`، PostgreSQL وRedis `ok`.
- TLS SAN يشمل الدومينات الأربعة؛ الشهادة حتى 2026-11-28.
- 5436/6381/8005 بقيت loopback-only.
- Backend/Celery/Nginx logs بعد النشر: صفر
  `traceback|critical|fatal|emerg`.
- `resort-os-healthcheck.service`: `Result=success`، وصفر وحدات systemd
  فاشلة.
- endpoint التقييم المنشور أعاد 422 بدون `X-Guest-Session` كما يجب بدل
  404، وصورة Backend تحمل رابط Google المعتمد حرفيًا.
- الفحص البصري من المتصفح فتح تطبيق الموظفين بالجلسة الحالية، ثم POS الحي
  وأظهر الكافيه والمطعم و12 طاولة وحالة الوردية. الموقع العام ظهر كاملًا،
  ومسار QR غير صالح عرض رسالة واضحة وزر `Try Again` بدل تعليق الصفحة.

## المتبقي التشغيلي

النشر الفني مكتمل. المتبقي فقط UAT على أجهزة Lenovo/التاتش الفعلية ومع
موظفي الكاشير والويتر، ثم عملية حقيقية `served → paid → rating` على QR
طاولة وHub غرفة للتحقق التشغيلي من أن 4–5 تعرض Google وأن 1–3 تبقى داخل
النظام. لم ننفذ معاملة دفع أو تقييمًا وهميًا على إنتاج المنتجع.
