# ACC-01 / REL-04 — Staff onboarding control plane and production release

**التاريخ:** 2026-07-30
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** WORKFLOW DEPLOYED — REAL ACCOUNTS PENDING APPROVED ROSTER

## 1. النتيجة

نُشرت دورة الموظف والحساب على إنتاج الخيمة:

1. الموارد البشرية تنشئ سجل الموظف داخل الفرع الفعال.
2. السوبر أدمن يفتح مركز الإدارة الموحد ويختار سجل الموظف.
3. السوبر أدمن يحدد الدور وينشئ حساب الدخول تحت Step-Up.
4. Backend يربط الحساب بالموظف، وينشئ عضوية الفرع الافتراضية الفعالة،
   ويسجل Audit داخل العملية نفسها.

دُمجت إدارة المستخدمين والصلاحيات في مركز واحد، ونُظمت القائمة الجانبية
حسب مجالات التشغيل والمالية والمخزون والنظام، وأصبح عرض الهاتف off-canvas.
لا يوجد سبب تقني معروف للـrollback وقت التسليم.

لم تُنشأ حسابات أو كلمات مرور وهمية. حالة الإنتاج بقيت:
`users=1`, `active_superadmins=1`, `branches=1`, `employees=0`,
`active_memberships=1`.

## 2. قواعد الحسابات المثبتة

- HR ينشئ سجل الموظف فقط، ولا يقبل endpoint الإنشاء `user_id`.
- المحاسب لا يملك صلاحية إدارة سجلات HR لمجرد مساواة المستوى الرقمي.
- المحاسب وبقية الموظفين حسابات عادية: سجل HR أولًا ثم حساب من واجهة
  السوبر أدمن.
- حساب `super_admin` إضافي لا يُنشأ من الواجهة؛ يستخدم bootstrap موثقًا
  من الطرفية بعد تسمية مالكه.
- provisioning محصور في الفرع الفعال، ويرفض الموظف التابع لفرع آخر أو
  المنتهي.
- الربط اليدوي القديم صار مسار استعادة للسوبر أدمن فقط؛ لا يربط
  `super_admin` ولا حسابًا بلا عضوية فعالة في الفرع نفسه.
- إنشاء الحساب والربط وعضوية الفرع وأحداث Audit تتم بخدمة Backend؛
  الواجهة ليست مصدر الصلاحية.

## 3. المصدر المراجع

- branch:
  `claude/CX-02C-frontend-auth-bootstrap`
- source commit:
  `679f76e` — `feat: unify staff onboarding control plane`
- remote branch كان يطابق `679f76e` قبل النشر.
- `origin/main` بقي عند `598938e` ولم يُحرّك.
- ملف المستخدم `scripts/wait-dns-then-switch.sh` لم يُعدل أو يُشغّل أو
  يُضمّن في commit أو archive.

## 4. بوابة الجودة

- full backend:
  `2181 passed, 40 skipped` من `2221 collected`، صفر failure.
- onboarding/HR/auth focused:
  `228 passed, 1 skipped`.
- آخر فحص أمني لمسار الربط:
  `31 passed`.
- frontend:
  `95 passed` عبر 13 ملفًا.
- frontend type-check: passed.
- i18n strict parity:
  العربية والإنجليزية `6002` مفتاحًا لكل منهما عبر 55 ملفًا.
- production frontend build: passed.
- `scripts/agent-check.sh`: passed.
- Alembic single head:
  `88d1c505a9dc`.
- `git diff --check`: passed.
- المراجعة البصرية المحلية لشاشتي HR والسوبر أدمن، ومنها deep-link
  والتعبئة المسبقة، اجتازت دون runtime errors.

تحذير Vite الوحيد هو chunk رئيسي أكبر من 500KB؛ ليس خطأ بناء، ويظل تحسين
performance لاحقًا.

## 5. أرشيف الإصدار ونقطة الرجوع

- active release:
  `/opt/resort-os-current -> /opt/resort-os-releases/679f76e`
- source archive:
  `/var/backups/resort-os/source-releases/679f76e.tar.gz`
- source SHA-256:
  `3e8b9a2b88746f93dd578d17dc2f010c0c63e21ccb9a5f82c1c40bff856110a8`
- تطابق SHA محليًا وعلى الـVPS قبل الاستخراج.
- production env نُقل إلى الإصدار الجديد بصلاحية `0600` دون عرض أسرار،
  و`validate_prod_env.py` نجح.
- rollback tags:
  `resort-os-rollback/*:pre-679f76e`
- rollback manifest:
  `/var/backups/resort-os/source-releases/679f76e-rollback-images.txt`
- manifest SHA-256:
  `d88564a27476f142fe7dfc29e79f7dac0c8777398f424d948b74232f910ca085`
- pre-cutover DB dump:
  `/var/backups/resort-os/database/resort_os_20260730_062529.dump`
- DB dump bytes:
  `559811`
- DB dump SHA-256:
  `bce5553a9b58d7a930c650c3f8618b7714a9a1db557e067977cc23beec10ab5a`
- `pg_restore --list`: passed قبل البناء.

## 6. النشر

- Compose domain config validation: passed.
- import canary من الصورة الجديدة طبع `El Kheima Beach`.
- `alembic heads` و`upgrade head`: passed؛ بقيت القاعدة عند
  `88d1c505a9dc`.
- استُبدلت الخدمات بالترتيب:
  Backend، ثم Celery worker/beat، ثم El Kheima، ثم Nginx.
- انتظر النشر health بعد كل مرحلة قبل المتابعة.
- PostgreSQL وRedis لم يُعاد إنشاؤهما.
- Marketing لم يتغير ولم يُعد بناؤه؛ بقي على صورته المراجعة ومصدره
  المستقل:
  `/opt/elkheima-marketing-current -> .../e5e122a`.

Image evidence:

- Backend:
  `sha256:7d27ae3a4b7daa38fe878b95c322bd1a7a1f2d5088990aa642163945441d73bc`
- Celery worker:
  `sha256:371eb2eab1dac5ad18de738a30bd522daa916b412d4e9b4883ba2a148f9e18ea`
- Celery beat:
  `sha256:df6030ab9d1679f0f16ca655c43d42bd99d16260d3f584bceb7664d4955bd794`
- El Kheima:
  `sha256:b638351fb3abebea2fa038cb39d26ab3c7632bf71f2e677b0830f27591e8feb1`
- Marketing unchanged:
  `sha256:ceffe9aff37f51cdf3a566d144eedad3acb94ab2665acf59f6fe0c04169cb0db`
- Nginx:
  `sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46`

Backend وCelery وEl Kheima وNginx تحمل working directory
`/opt/resort-os-releases/679f76e`. حاوية Marketing بقيت عمدًا على label
الإصدار السابق لأنها لم تُستبدل؛ مصدر Marketing المستقل نفسه لم يتغير.

## 7. قبول الإنتاج

- 8/8 containers Running.
- healthchecks المعرّفة: healthy.
- الحاويات الثماني: `RestartCount=0`.
- `https://elkheima.com/`: 200 وعنوان الصفحة التسويقية صحيح.
- `https://www.elkheima.com/`: 200 وعنوان الصفحة التسويقية صحيح.
- `https://app.elkheima.com/`: 200 وعنوان `Resort OS`.
- `https://app.elkheima.com/health`: `status=ok` مع DB وRedis سليمتين.
- PostgreSQL `5436` وRedis `6381` وBackend `8005` بقيت loopback-only.
- TLS SAN:
  `elkheima.com`, `www.elkheima.com`, `app.elkheima.com`.
- TLS expiry:
  `2026-10-28 02:21:34 UTC`.
- healthcheck systemd manual run:
  `Result=success`, `ExecMainStatus=0`.
- backup/health/certbot timers: active.
- failed systemd units: 0.
- severe log scan: صفر أخطاء. التطابق النصي الوحيد الأولي كان اسم مهمة
  Celery مشروعة `notify_critical_work_order` وليس سجل CRITICAL.

## 8. المتبقي

1. اعتماد roster حقيقي: الاسم، البريد، الدور، المدير، وبيانات HR اللازمة.
2. ينشئ HR سجل كل موظف، ثم ينشئ السوبر أدمن حسابه من مركز الإدارة.
3. تسمية مالك `super_admin` الاحتياطي ثم إنشاؤه عبر bootstrap من الطرفية.
4. تنفيذ UAT بالأدوار على هاتف وجهاز موظف بالعربية والإنجليزية.
5. مراجعة بيانات العرض واستبدال ما يلزم ببيانات master معتمدة.
6. اختيار قناة خارجية لتنبيهات health gate.

المرجع التدريبي:
`docs/STAFF_APP_GUIDE_AR.md`.

المرجع الأمني:
`docs/SUPER_ADMIN_GUIDE_AR.md`.
