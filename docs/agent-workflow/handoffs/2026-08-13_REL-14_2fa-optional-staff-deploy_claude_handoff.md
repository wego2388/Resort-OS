# Handoff — REL-14: نشر دفعة 2FA الاختياري للموظفين + تراكم غير موثّق سابق

**التاريخ:** 2026-08-13
**Branch:** `main` (`origin/main` up to date، لا commits جديدة أُنشئت في هذه الجلسة)
**Commit المنشور:** `95c30d9` (كان `8cd4860` فعّال على الإنتاج قبل هذه الجلسة، بدون أي توثيق سابق)
**الحالة:** منشور ومتحقق فعليًا على الإنتاج ✅

---

## طلب Mohamed

"عايز ارفع المشروع علي الفي بي اس بطريقتك" — لا أوامر تفصيلية، تفويض
لاختيار الطريقة الصح، فاتُبع `DEPLOYMENT.md` (الـrunbook الرسمي الحالي:
immutable release + domain TLS)، **وليس** `docs/DEPLOYMENT_2FA_FIX.md`
الموجود مسبقًا في الشجرة — الأخير كان يشاور على فرع قديم
(`claude/CX-02C-frontend-auth-bootstrap`، بينما الفرع الفعلي الحالي هو
`main`)، مسار نشر قديم (`/opt/resort-os`، موثّق صراحةً في `DEPLOYMENT.md`
كـ"legacy source snapshot; not a deploy target")، وIP-only TLS بدل
الدومين الحقيقي — اتّباعه حرفيًا كان هيكسر التوافق مع كل نسخ اليوم.

## اكتشاف: 16 commit كانت فعّالة/مدفوعة لكن غير موثّقة إطلاقًا

`git status` عند بدء الجلسة: `main` نظيف و**up to date مع origin** — أي
كل الـ16 commit من `8fbda3c` (آخر حالة موثّقة في `PROJECT_STATUS.md`،
REL-13) كانت مكتوبة ومدفوعة لـ`origin/main` بالفعل. لكن الإنتاج الفعلي
على الـVPS كان لسه واقف على `8cd4860` (منتصف السلسلة)، و`PROJECT_STATUS.md`
لم يُحدَّث منذ REL-13 — أي فجوة توثيق حقيقية، مش مجرد تأخر رفع.

من الـ16: تسعة عشرة commit توثيقي (CX-02C→CX-02G handoffs) كانت موجودة
بالفعل وتغطي معظم إصلاحات الواجهة (layout/overflow/tables/WS)، لكن
handoff الأخير (CX-02G) كان يذكر "منشور على الإنتاج ✅" رغم أن الـVPS
وقتها كان لسه على commit أقدم — ادّعاء غير دقيق، مصحَّح هنا بأول تحقق
فعلي حقيقي على الإنتاج بعد هذا الـrelease.

**غير موثَّق قبل هذا الـhandoff إطلاقًا:**
- `8cd4860` — منيو الآيس كريم بسعر نهائي شامل الضريبة/الخدمة (migration
  `d1e2f3a4b5c6`، `dining_tax_inclusive_list_prices`).
- `4df8164` — استبدال `float` بـ`Decimal` في schemas مالية (`dining`
  `OutletSalesReport`، `analytics` `RevenueBucket`/`RevenueSummary`/
  `DashboardRevenue`/`DailyStatsRead`/`EnergyKPIs`) — إصلاح دقة حقيقي،
  مش تجميلي، على أرقام تُعرض في تقارير مالية فعلية.
- `bd8e580` + `b9dd5ef` — راجع القسم التالي.
- `95c30d9` — `docs/DEPLOYMENT_2FA_FIX.md` نفسه (دليل قديم/غير دقيق، راجع
  أعلاه — **لا تنفّذه كما هو في أي جلسة قادمة**).

## التعديل الجوهري لهذه الدفعة: 2FA اختياري للموظفين العاديين

قرار Mohamed المباشر (موثّق في رسالة الـcommit نفسها): 2FA (Google
Authenticator) يبقى إجباري بس لـ`super_admin`/`accountant`/`owner`
(`MANDATORY_2FA_ROLES` في `backend/app/core/deps.py`)؛ باقي الأدوار
(cashier, waiter, receptionist...) يسجّلوا دخول بإيميل+باسورد بس.

**التنفيذ (`bd8e580`)**: `AuthService.provision_staff_account` بقى بيحسب
`requires_2fa_bootstrap = role in MANDATORY_2FA_ROLES` قبل إنشاء اليوزر —
لو `False`: `enrollment_token`/`enrollment_expires_at` يرجعوا `None`،
`two_factor_bootstrap_required=False`. الأدوار الحساسة سلوكها **بدون أي
تغيير**. اتأكد بتست جديد صريح يثبت `accountant` لسه بياخد enrollment_token
كامل. الـFrontend (`SuperAdminView.vue`) بيعرض enrollment_token بس لو
موجود فعليًا.

**الحسابات القديمة اللي فعّلت 2FA قبل هذا التعديل** (`b9dd5ef`):
`backend/scripts/disable_2fa_for_regular_staff.py` — سكريبت تفاعلي
(بيطبع القائمة، بياخد تأكيد صريح `yes`/`no` قبل أي تعديل)، بيعطّل 2FA
بس للأدوار غير الموجودة في `MANDATORY_2FA_ROLES`. **لم يُشغَّل بعد على
الإنتاج في هذه الجلسة** — قرار تشغيلي منفصل، يحتاج Mohamed يحدد هل فيه
فعليًا حسابات موظفين عاديين فعّلت 2FA قبل كده تستحق التشغيل.

## بوابة التحقق المحلي (كاملة قبل أي نشر، DEPLOYMENT.md §5.A)

- `bash scripts/agent-check.sh` → PASS (alembic head واحد `d1e2f3a4b5c6`،
  2817 اختبار مجمّع، Compose config صحيح، لا whitespace).
- `pytest tests/ -q` (backend) → exit 0 (بدون رجوع، القيمة النهائية
  محجوبة بـ`-q` — نفس ملاحظة `CLAUDE.md`، exit code هو الدليل).
- `pnpm run type-check:all` → نظيف (el-kheima + owner).
- `pnpm --filter el-kheima test:frontend` → **103/103 نجحوا**.
- `pnpm run build:all` (+ `owner`) نظيف؛ بناء `el-kheima` وحده يحتاج
  `VITE_PUBLIC_SITE_URL` (مطلوب فعليًا في وقت البناء الحقيقي على الـVPS
  عبر `.env.prod` — تم التأكد محليًا بتزويد القيمة يدويًا، مش باج).

## النشر الفعلي (DEPLOYMENT.md §5 B→E)

1. `git archive` من `95c30d9` → SHA-256 محسوب محليًا وعلى الـVPS ومطابق
   (`272a671e...`).
2. استخراج في `/opt/resort-os-releases/95c30d99f...` جديد (لم يُستبدَل
   أي release موجود).
3. **باج إنتاج حقيقي اتكشف واتصلح أثناء النسخ**: `.env.prod` الخاص بالـ
   release الفعّال السابق (`8cd4860`) كان `root:root 0600` بدل
   `resortos:resortos` — يعني `resortos` (المستخدم اللي كل الـautomation
   بتشتغل بيه) مايقدرش يقراه. اتصلح بالنسخ عبر `sudo cp` + `chown
   resortos:resortos` + `chmod 0600` للـrelease الجديد (المحتوى اتنسخ من
   غير أي طباعة). **هذا الباج كان بيكسر `resort-os-backup.service`
   بصمت من `2026-08-13 03:02` (أول تشغيل بعد ما `8cd4860` بقى فعّال) —
   يعني آخر نسخة احتياطية حقيقية ناجحة قبل هذه الجلسة كانت من
   `2026-08-12 03:00`، أكتر من 13 ساعة بدون backup سليم، بصمت، من غير
   أي تنبيه ظاهر.** اتأكد الإصلاح فعليًا بتشغيل يدوي لـ
   `resort-os-backup.service` بعد تحديث `/opt/resort-os-current` —
   نجح، وبما إن كل release جديد بينسخ `.env.prod` من السابق، المشكلة
   متحلّة بشكل دائم للـreleases القادمة مش حل مؤقت.
4. `python3 scripts/validate_prod_env.py` → PASS.
5. Rollback point: صور `backend`/`el_kheima`/`marketing_site`/`nginx`
   الحالية اتحطتلها tag `resort-os-rollback/*:pre-95c30d9...`، السجل في
   `/var/backups/resort-os/source-releases/95c30d9...-rollback-images.txt`.
6. Backup طازج قبل أي تغيير: `resort_os_20260813_163841.dump` (732K) —
   اتأكد بـ`pg_restore --list` (1547 TOC entries) قبل الاستمرار.
7. Build (`backend`/`el_kheima`/`marketing_site`) نظيف. Preflight: import
   check نظيف (بدون تحذير SECRET_KEY ضعيف — أسرار الإنتاج قوية)،
   `alembic heads` على الصورة الجديدة = `d1e2f3a4b5c6` = نفس نسخة الـDB
   الحالية (لا migration جديدة فعليًا — `alembic upgrade head` نُفِّذ
   وكان no-op كما هو متوقع).
8. استبدال متحكَّم فيه بالترتيب: `backend` → `celery_worker`+`celery_beat`
   → `el_kheima`+`marketing_site` → `nginx` (force-recreate)، مع health
   check بعد كل مرحلة. صفر `RestartCount`، صفر خطأ/traceback في اللوجات.
9. تبديل `/opt/resort-os-current` للـrelease الجديد.

## القبول النهائي (DEPLOYMENT.md §6) — كله نجح

- `backend`/`celery_worker`/`celery_beat` نفس الـimage ID بالظبط ونفس
  `org.opencontainers.image.revision=95c30d99f...`.
- الأربع نطاقات (`elkheima.com`, `www.elkheima.com`, `app.elkheima.com`)
  HTTP 200؛ `app.elkheima.com/health` → `{"status":"ok",...}`.
- `alembic current` على الحاوية الحية = `d1e2f3a4b5c6 (head)`.
- `users=11`, `branches=1` — أرقام منطقية، مفيش فقد بيانات.
- TLS SAN يشمل `elkheima.com`/`www.elkheima.com`/`app.elkheima.com`
  (وكمان `owner.elkheima.com`، تطبيق Owner Cockpit شغال بالفعل من قبل
  هذه الجلسة، لم يُلمَس هنا).
- DB/Redis لسه loopback-only (`127.0.0.1:5436`/`127.0.0.1:6381`).
- صفر error/critical/fatal/traceback حقيقي في لوجات backend/celery/nginx.
- `systemctl start resort-os-healthcheck.service` يدويًا → **14/14 نجحت**
  (بعد إصلاح الـbackup أعلاه — قبله كانت 1 فشل بس بسبب نفس الباج).

## ما لم يُفعل عمدًا في هذه الجلسة

- **`disable_2fa_for_regular_staff.py` لم يُشغَّل على الإنتاج** — يحتاج
  قرار Mohamed مباشر (فيه حسابات موظفين عاديين فعّلوا 2FA فعليًا قبل
  كده؟ لو آه، شغّله بعد ما يتأكد الأسماء).
- **الـ`docs/DEPLOYMENT_2FA_FIX.md`** لم يُحذف — تُرك كأثر، لكن **لازم
  يُعتبر تاريخي/غير دقيق** لأي جلسة قادمة (نفس معاملة `docs/archive/`
  فعليًا، رغم إنه مش موجود هناك فعليًا — يستحق نقل لـ`docs/archive/`
  لاحقًا، لم يُنقَل هنا لتفادي توسيع نطاق هذه الدفعة عن طلب النشر نفسه).

## Rollback

`/var/backups/resort-os/source-releases/95c30d99fc9a07ccf8495bf555a87b5e926fefbf-rollback-images.txt`
فيه IDs الصور السابقة (كل الحاويات كانت على `8cd4860`). نسخة DB مباشرة
قبل هذا الـrelease:
`/opt/resort-os-releases/95c30d99fc9a07ccf8495bf555a87b5e926fefbf/backups/resort_os_20260813_163841.dump`
(SHA غير محسوب صراحةً هنا، لكن `pg_restore --list` تحقق من سلامتها).
