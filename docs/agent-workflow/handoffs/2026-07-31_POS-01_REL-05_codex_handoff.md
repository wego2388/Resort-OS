# POS-01 / REL-05 — Multi-outlet order fix and production release

**التاريخ:** 2026-07-31
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. النتيجة

نُشر إصلاح تبديل المنفذ في شاشة الـPOS الموحدة. عندما يكون الطلب محفوظًا
في الـBackend (`pendingOrderId` موجود)، يغيّر الكاشير المنفذ المعروض ويحمل
المنيو الجديدة دون إلغاء الطلب أو إظهار dialog. إذا كانت الأصناف ما زالت
سلة محلية فقط، تبقى نافذة التأكيد والإلغاء الحالية كما هي.

الملف المتغير:
`frontend/apps/el-kheima/src/views/pos/UnifiedPOSView.vue`.

لا يوجد تغيير Backend أو API أو schema أو بيانات أو DNS أو TLS أو
Marketing.

## 2. المصدر

- branch: `claude/CX-02C-frontend-auth-bootstrap`
- commit: `a3e8abb` — `fix(pos): preserve pending order when switching outlets`
- commit مدفوع إلى الفرع نفسه؛ `origin/main` لم يتحرك.
- release: `/opt/resort-os-releases/a3e8abb`
- current: `/opt/resort-os-current -> /opt/resort-os-releases/a3e8abb`
- archive: `/var/backups/resort-os/source-releases/a3e8abb.tar.gz`
- archive SHA-256:
  `2ff370284727ae57688c4efda9dad22db2729abf45fbbfe3dc276e78d7388bad`

## 3. بوابة الجودة

- `scripts/agent-check.sh`: passed.
- full Backend regression: 2181 passed، 40 skipped، صفر failure.
- Alembic: single head `88d1c505a9dc`.
- i18n strict validation: 6002 مفتاحًا لكل من العربية والإنجليزية.
- Frontend: 95/95 tests عبر 13 ملفًا.
- `pnpm run type-check:all`: passed.
- El Kheima production build مع
  `VITE_PUBLIC_SITE_URL=https://elkheima.com`: passed.
- `git diff --check`: passed.

تحذير chunk أكبر من 500KB بقي تحذير أداء غير حاجز، وليس خطأ بناء.

## 4. نقطة التراجع

- pre-release DB:
  `/var/backups/resort-os/database/resort_os_20260731_210536.dump`
- DB SHA-256:
  `5dd553f00433f0d7b70e3fcd54518c3c0c1770494efe6c4429dbd2858720aa1d`
- `pg_restore --list`: passed.
- rollback tags: `resort-os-rollback/*:pre-a3e8abb` للخدمات الست.
- rollback manifest:
  `/var/backups/resort-os/source-releases/a3e8abb-rollback-images.txt`
- manifest SHA-256:
  `f904b6922081b17630814893708e39a543614d8652c2ce974922ec0fbd8f8fec`

لا يحتاج rollback تطبيقي متوافق إلى استعادة قاعدة البيانات.

## 5. النشر

- production env نُقل إلى الإصدار بصلاحية `0600`، وvalidation نجح دون
  عرض الأسرار.
- Compose domain config: passed.
- بُنيت خدمة `el_kheima` فقط، ثم اجتازت canary على منفذ loopback.
- استُبدلت `el_kheima` وانتُظر health، ثم أُعيد إنشاء Nginx لالتقاط عنوان
  الحاوية الجديدة.
- PostgreSQL وRedis وBackend وCelery وMarketing لم تُعد إنشاؤها أو بناءها.
- Backend وCelery بقيا على release `679f76e`؛ Staff وNginx يحملان label
  release `a3e8abb`.

Staff image:
`sha256:397ae1ab6fb44c34b2d27b95f2313a1ee43d126ec6f7aed52a2b017d5de78fb8`.

## 6. قبول الإنتاج

- `elkheima.com`, `www.elkheima.com`, `app.elkheima.com` و`/health`:
  HTTP 200.
- عنوان تطبيق الموظفين: `Resort OS`.
- Bundle `UnifiedPOSView` المنشور طابق البناء المحلي؛ SHA-256:
  `0339d0eb7ca8c93a9a9fa081d74e13c6b47a6bc78d9940bfa8b2a024388dea87`.
- 8/8 containers Running؛ كل healthchecks المعرّفة سليمة؛
  `RestartCount=0` للجميع.
- Backend health: DB وRedis `ok`.
- Alembic production current: `88d1c505a9dc (head)`.
- قاعدة البيانات بقيت `users=1`, `branches=1`.
- المنافذ 5436/6381/8005 بقيت loopback-only؛ 80/443 عامة.
- TLS SAN للدومينات الثلاثة وصالح حتى `2026-10-28 02:21:34 UTC`.
- severe logs لخدمات التطبيق الست: صفر خلال نافذة النشر.
- healthcheck اليدوي: `Result=success`, `ExecMainStatus=0`.
- backup/health/certbot timers: active؛ failed systemd units: 0.

لم يُنفذ rollback لأن كل شروط القبول نجحت.
