# REL-13 — Financial Integrity + Fractional Ownership

**الحالة:** COMPLETE / DEPLOYED
**تاريخ النشر:** 2026-08-11
**الإصدار الفعال:** `/opt/resort-os-releases/8fbda3c`
**Source commit:** `8fbda3c752d5f877fc17f4d7dbd5558b0461d57a`
**Implementation commit:** `6e8d79cf1018afc26e457a8fb9fe9015e5015255`
**CLI registry commit:** `9bf07bbd98493428986d900e5b0353c6cb68bafb`
**Owner PWA hotfix:** `8fbda3c752d5f877fc17f4d7dbd5558b0461d57a`

## ما تغير

- استبدال الاسم الظاهر السابق بالاسم المعتمد «الملكية الجزئية» في
  Staff/Owner/i18n والأدلة والتقارير. بقيت أسماء API والجداول والكلاسات
  والأدوار `timeshare*` ثابتة عمدًا للتوافق.
- إضافة Payment موحد لتحصيلات الإيجارات وأقساط/صيانة/ردود الملكية الجزئية،
  مع اشتراط وردية مفتوحة للكاش وتسجيل المحصل الحقيقي.
- جعل القيود المالية الصارمة idempotent عبر source/source_id/reference.
- إلغاء سلفة الموظف يعكس الصرف ذريًا ويسجل cancelled_by/cancelled_at.
- رد عقد الملكية الجزئية مقفول row-level، محدود بصافي المحصل، مرتبط بطريقة
  الرد والمستخدم، وله قيد عكسي وAuditLog.
- الاستلام الجزئي لأمر الشراء يستخدم StockMovement كمفتاح لكل دفعة؛ فشل
  الحسابات المحاسبية يرجع المخزون والأمر والحركة كلها.
- إضافة مصالحة dry-run-first لرسوم PMS المبكرة/المتأخرة وbackfill لاستحقاقات
  الإيجار، مع PostgreSQL advisory locks ومستخدم إنتاج حقيقي.
- تصحيح Owner totals قبل limit، ABC، توقيت القاهرة، وpagination للتفاصيل.
- backend/worker/beat تستخدم صورة واحدة عليها OCI revision مطابق للcommit.
- إضافة وسم PWA العام `mobile-web-app-capable` بجانب وسم Apple؛ التحذير
  اختفى سببه من HTML المبني والحي دون تغيير المصادقة.

## Migrations

مسار الإنتاج الفعلي:

`b7c8d9e0f1a2 -> 90f2a4c81b3e -> a7b8c9d0e1f2 -> b8c9d0e1f2a3 -> c9d0e1f2a3b4`

التحقق الحي أعاد `c9d0e1f2a3b4 (head)`، والأعمدة الجديدة `2|3` والـFK
`fk_timeshare_contracts_cancelled_by_users` موجود.

## بوابات ما قبل النشر

- backend كامل: `2806` اختبارًا، 100%، exit 0، صفر failures.
- Staff frontend: `103/103`؛ i18n العربية والإنجليزية `6313/6313`.
- `type-check:all` و`build:all` و`agent-check.sh` نجحت.
- PostgreSQL 16 فارغ: upgrade إلى head، downgrade إلى `90f2a4c81b3e`، ثم
  re-upgrade إلى head نجحت.
- Gitleaks على staged release: صفر leaks؛ Compose dev/prod وdiff-check نجحت.
- اختبار CLI المستقل بعد إصلاح registry: PMS وLeasing passed؛ 17 اختبارًا
  مركزًا passed.
- Owner hotfix: `pnpm --filter owner build` و`type-check` نجحا، وملف `dist`
  احتوى الوسمين، ثم نجح `agent-check.sh` قبل إصدار commit التصحيح.

## النسخ والـrollback

- DB dump الطازج قبل hotfix:
  `/var/backups/resort-os/database/resort_os_20260811_123803.dump`
- الحجم: `727640` bytes؛ TOC: `1547`.
- SHA-256:
  `53d269039128ba78848bbf74e0176f4999a14444bda72b013696c075dfa8a37d`
- Exact source archive:
  `/var/backups/resort-os/source-releases/8fbda3c.tar.gz`
- Source SHA-256:
  `963675229d730cc961a07ab8c064eddb82cf396ea344b8a86ffbc5679d96fb7b`
- Rollback manifest:
  `/var/backups/resort-os/source-releases/8fbda3c-rollback-images.txt`
- Manifest SHA-256:
  `29b90a996d79316a1efe85fbfdaa1b76bd0377c95e52740a94903ff7877e4f0b`

لا تسترجع DB لمجرد rollback تطبيق؛ استخدم صور manifest أولًا. استرجاع dump
مسموح فقط عند ثبوت فساد بيانات، لأن المصالحة أضافت قيودًا صحيحة مقصودة.

## مصالحة الإنتاج

- PMS early/late: `2` قيود، إجمالي `250.00 EGP`.
- Leasing accruals: `5` دفعات، إجمالي `138000.00 EGP`.
- إعادة dry-run: PMS `proposed_count=0`، Leasing `proposed_count=0` و
  `broken_accrual_count=0`.

## قبول الإنتاج

- `elkheima.com` و`www` و`app` و`owner`: HTTP 200.
- health وready: DB/Redis `ok`؛ protected probes: 401.
- backend/worker/beat image ID واحد:
  `sha256:edbb4cc455d83cb058a38609d59c0640f1fe30ad535187d5377b0c9ba9679da7`.
- OCI revision للخدمات الثلاث:
  `9bf07bbd98493428986d900e5b0353c6cb68bafb`.
- Owner image:
  `sha256:41f7e251b1cb3f651ec5116bce621e233a5edae71d0ffe01163b46688667a4a1`؛
  الوسمان العام وApple موجودان داخل الحاوية، والعام موجود في HTML الخارجي.
- كل الخدمات المتغيرة `RestartCount=0`؛ strict log window بعد الاستقرار صفر
  Traceback/ERROR/CRITICAL/FATAL.
- Staff وOwner live bundles: صفر للاسم القديم، و«الملكية الجزئية» موجودة.
- DB/Redis ما زالا loopback-only على `127.0.0.1:5436` و`127.0.0.1:6381`.
- TLS SAN يغطي apex/www/app/owner؛ systemd healthcheck Result=success وexit 0.
- تحليل صور الكونسول من سجل الإنتاج: Owner refresh 200 ثم logout موثق، وبعده
  401 بلا جلسة؛ وStaff Incognito أعاد refresh 401 ثم login 401 ثم login 200
  وbootstrap 200. لا توجد أحداث `refresh_token_replayed` في النافذة كلها.

ملاحظة تشغيلية: ظهرت خمس 502 في Nginx خلال ثانية إعادة backend بينما جلسة
Owner حية كانت تطلب البيانات؛ بعد استقرار backend كانت نافذة السجلات صفر
أخطاء وعادت كل الطلبات والـhealth طبيعيًا.
