# Handoff — REL-15: Auth, Operations, Single Branch, Timeshare, Owner Readiness

**التاريخ:** 2026-08-14
**Branch:** `codex/rel-15-auth-ops-readiness` (مدفوع إلى origin)
**Implementation baseline commit:**
`6f1f6e1c703f2ecb88851691864525e22e5071d5`
**Current runtime commit (account cleanup follow-up):**
`85da3f8bcd7421b86f156748ad874b378b8bdc54`
**Production:** منشور ومتحقق فعليًا ✅
**Active release:**
`/opt/resort-os-releases/85da3f8bcd7421b86f156748ad874b378b8bdc54`
**Alembic:** `e2f3a4b5c6d7 (head)`

## 1. قرارات Mohamed المنفذة

- الحقيقة التشغيلية فرع واحد فقط واسمه حرفيًا
  `El Kheima Beach Resort`؛ لا branch chooser/switcher في رحلة المستخدم.
- كل شخص فعلي له حساب باسمه؛ ممنوع حساب مشترك باسم القسم أو الوردية.
- تحصيل الملكية الجزئية افتراضيًا لمدير الوحدة؛ الموظف يحتاج permission
  صريحًا باسمه، والتحصيل له بطاقة/بنك فقط بلا cash.
- الرواتب الحالية تشغيل داخلي، وليست ادعاء امتثال ضريبي/تأميني مصري قبل
  اعتماد متخصص.
- البيانات الحالية تجريبية، لكن لم يحدث حذف جماعي لأن المصالحة الآمنة أصلحت
  عضويات الفرع دون فقد معلومات، والـroster الحقيقي سيستبدل الحسابات لاحقًا.
- فكرة S Pen محفوظة لتحسين لاحق: ملاحظات نصية خاصة بالمالك فقط عبر تحويل
  الكتابة اليدوية إلى نص؛ لم تُنفذ في REL-15 حتى لا تتضخم النسخة قبل UAT.

## 2. ما أُصلح

### Auth و2FA والجلسات

- البريد canonical/case-insensitive مع unique index على `lower(email)`؛
  preflight الإنتاج أثبت صفر collision قبل migration.
- كلمة المرور opaque؛ أُلغي `trim()` في الواجهة والخادم.
- حد IP المشترك للدخول أصبح `60/300s`، مع `Retry-After`، بينما قفل كلمة
  المرور وOTP ما زال لكل حساب بعد المحاولات الفاشلة.
- refresh واحد عبر tabs باستخدام Web Locks مع localStorage lease fallback؛
  يمنع إلغاء refresh family بسبب سباق tabs.
- `force_reset_2fa` يمسح recovery codes والجلسات ويوقف access tokens ويسجل
  Audit؛ الدور الإلزامي يحصل على enrollment proof جديد وحيد المرة.
- المالك والمحاسب والسوبر أدمن: كلمة مرور مؤقتة ثم تغييرها ثم 2FA وأكواد
  استرداد. الموظفون العاديون: بريد وكلمة مرور فقط.
- حالات الحساب المقفول وغير النشط ورسائل 429 أصبحت مفهومة في الواجهتين.
- السكربت القديم غير الآمن لتعطيل 2FA أصبح fail-closed، وكذلك entry points
  القديمة `deploy.sh` و`sync-deploy.sh` و`switch-to-domain.sh`؛ المرجع الوحيد
  هو `DEPLOYMENT.md`.

### الأدوار والفرع

- accountant landing أصبح `/admin/finance` بلا redirect loop.
- named-role outer gates للمالية وHR وCRM وPMS/POS والحجوزات والتشغيل
  وWebSockets؛ المتخصص لا يرث وحدة أخرى لمجرد ارتفاع الرقم.
- `timeshare_admin` معزول عن cashier/finance/POS، وowner معزول read-only.
- إنشاء حساب staff من الويب يتطلب `employee_id`؛ إنشاء أول
  `timeshare_admin` أصبح مدعومًا.
- bootstrap المالك يضيف عضوية الفرع الوحيد ذريًا؛ أداة reconciliation
  production-safe تعمل dry-run افتراضيًا، لا تحذف ولا تخمن HR link.

### الملكية الجزئية والزيارات وخدمة العملاء

- إنشاء موظف الوحدة من سجلات HR المؤهلة.
- صلاحيات الأزرار والخادم متطابقة، والتحصيل للموظف يتطلب named override
  وطريقة غير نقدية.
- بوابة عامة فعلية في `/timeshare-portal`: OTP مقاوم enumeration، token،
  قراءة العقد والدفعات/PDF، طلبات زيارة، تذاكر دعم، وردود العميل.
- rate limits وownership/branch checks واختبارات HTTP موجودة.

### تطبيق المالك وResponsive

- أزيلت 24 artifact JavaScript مولدة قديمة كانت Vite قد تحمّلها بدل ملفات
  TypeScript/Vue المحدثة، وكانت سببًا محتملًا مباشرًا للشاشة السوداء.
- أصلحت رحلة temporary password و2FA وQR field وenrollment proof وأكواد
  الاسترداد والـrouter loops.
- App shell يعرض اسم المنتجع وعنوان الشاشة، وbottom nav لا يغطي آخر محتوى؛
  desktop side rail وdetail sheet محدود العرض.
- شاشة «الآن» decision-first: حالة التشغيل والتنبيهات، المؤشرات المثبتة،
  أموال اليوم، المطلوب تحصيله، ثم العمليات.
- كل شاشة تعرض freshness بتوقيت القاهرة وزر تحديث وتحذير stale data.
- Date range يستخدم تاريخ القاهرة المحلي، والنسب والأرقام عربية، وشاشات
  المبيعات والمصروفات والأداء والورديات وHR أوضح على الهاتف.
- Staff mobile header أصبح touch-first، وجداول HR/Finance/SuperAdmin لها
  mobile cards، وبوابة العميل responsive.

## 3. بوابات التحقق المحلي

- `bash scripts/agent-check.sh --full` → PASS.
- Backend: `2802 passed, 68 skipped` من `2870` بعد إضافة اختبار أداة
  الأرشفة المعزول.
- Staff unit: `106/106`؛ i18n `6323` key لكل لغة؛ mock responsive `8/8`.
- Owner responsive E2E `12/12`، تشمل `320`, `390`, `768`, `1024`, `1280`
  وSamsung-class `412×915`، وعدم تغطية bottom nav للمحتوى.
- Staff/Owner type-check وproduction build ناجحان.
- Migration من PostgreSQL فارغة حتى `e2f3a4b5c6d7` ناجحة، وhead واحد.
- التحذيرات غير الحاجبة: 12 SAWarning قديمة في اختبارات historical room
  inventory، وتحذير حجم bundle في Staff؛ لا failure.

## 4. نشر production

- exact source archive:
  `/var/backups/resort-os/source-releases/6f1f6e1c703f2ecb88851691864525e22e5071d5.tar.gz`
- SHA-256 مطابق محليًا وعلى VPS:
  `2975c4b4f5eda1fa6fd38872abb808cfa263353de98adc87df6862a42f07d7dc`
- environment validation نجح، مع mode `0600` وبدون طباعة أسرار.
- rollback images manifest:
  `/var/backups/resort-os/source-releases/6f1f6e1c703f2ecb88851691864525e22e5071d5-rollback-images.txt`
- DB dump قبل التغيير:
  `/var/backups/resort-os/resort_os_20260814_044024.dump`، `755975` bytes،
  واجتاز `pg_restore --list`.
- retention المعتاد حذف dumpين محليين أقدم من 14 يومًا، وأبقى 28 dump.
- بُنيت `backend`, `el_kheima`, `owner` فقط؛ Marketing لم يُبنَ أو يُستبدل.
- migration: `d1e2f3a4b5c6 -> e2f3a4b5c6d7`.
- replacement: backend → worker/beat → Staff/Owner → Nginx، مع health بعد
  كل مرحلة. تحديث symlink احتاج `sudo` بعد Permission denied أولي؛ الحاويات
  كانت healthy، ثم حُدث الرابط بنجاح دون rollback.

## 5. قبول production

- 9 حاويات Resort تعمل؛ كل `RestartCount=0`.
- backend/worker/beat image:
  `sha256:20b3b5584b5d0bd2e59abb56a49b3996bab010e4f36b3b0b166e26f21077ee4c`
  وبنفس revision `6f1f6e1...`.
- Staff image `sha256:708e5679...`، Owner `sha256:de31cbbf...`؛ Marketing
  بقي `sha256:4476a3c4...` وعلى release المستقل `088cab4...`.
- `elkheima.com`, `www`, `app`, `owner`, API health، portal page وportal
  config كلها HTTP 200؛ `/api/v1/auth/me` بلا auth يعيد 401.
- live browser read-only `6/6`: Owner login وStaff login وTimeshare portal
  على `412×915` و`1280×800`، بلا overflow/page error/unexpected HTTP.
  refresh 401 عند بدء صفحة عامة بلا cookie مستثنى كحالة تسجيل خروج متوقعة.
- TLS SAN: الأصل وwww وapp وowner؛ الانتهاء `2026-11-05 21:32:26 UTC`.
- DB/Redis ما زالا loopback-only على `127.0.0.1:5436/6381`.
- `resort-os-healthcheck.service` الجديد نجح `16/16`، والtimer active/enabled.
- log scan: لا traceback/critical/fatal/emerg حقيقي. المطابقة الوحيدة الأولية
  كانت اسم Celery task `notify_critical_work_order` وليست log severity.
- لا temporary release database متروكة.

## 6. مصالحة الحسابات

- قبل apply: 11 حسابًا تشغيليًا نشطًا؛ 5 memberships مفقودة، default واحد
  غير مضبوط، ولا reactivation.
- بعد apply: `operational_without_membership=0`؛ كل مالك نشط له عضوية
  (`2 active owners / 2 active owner memberships`).
- dry-run التالي: create/reactivate/default كلها قوائم فارغة.
- بعد اعتماد Mohamed قائمة الاحتفاظ، أُبقيت 4 حسابات فقط: سوبر أدمن،
  مالكان، ومدير Timeshare. لم تتغير أسماؤهم أو أدوارهم أو بيانات دخولهم.
- أداة `backend/scripts/archive_experimental_accounts.py` تعمل dry-run
  افتراضيًا وتغلق التنفيذ عند اختلاف العدد أو غياب حساب محمي أو عضوية
  الفرع. التنفيذ يحتاج actor سوبر أدمن محفوظًا وسببًا وعبارة تأكيد حرفية.
- dry-run الإنتاج استهدف 8 IDs فقط، ثم apply ذري: إخفاء الهوية وsoft-delete،
  إلغاء 8 عضويات، فك 4 روابط HR، وحذف 199 refresh token و16 recovery code
  و3 PIN و4 blacklist rows. لا توجد step-up grants أو permission overrides
  مستهدفة.
- فحص ما بعد التنفيذ: `visible_users=4`, `archived_users=8`,
  `protected_active_memberships=4`, وكل auth/HR/membership النشط للأهداف
  يساوي صفر؛ Audit موجود بمراجع الأرقام فقط. dry-run التالي وجد صفر أهداف.
- الحسابات الحقيقية الجديدة تُنشأ لاحقًا من
  `docs/templates/REL15_STAFF_ROSTER_TEMPLATE.xlsx`، حساب منفصل لكل شخص.

### نشر follow-up تنظيف الحسابات

- exact source archive SHA-256:
  `b0599b7ec6d9752ed435586d451921c2da1c6dbd44d65af1df50ebd1a9f45819`.
- DB dump قبل apply، متحقق بـ`pg_restore --list`:
  `/var/backups/resort-os/resort_os_20260814_071442.dump` (`757959` bytes).
- rollback manifest:
  `/var/backups/resort-os/source-releases/85da3f8bcd7421b86f156748ad874b378b8bdc54-rollback-images.txt`.
- بُني واستُبدل Backend/Worker/Beat فقط؛ Staff وOwner وMarketing وNginx لم
  تتغير. الثلاثة على image `sha256:2c03392b275cb149f1f3b516e877accf93b3942fe90f2a50cdc5e6b85f7f77f0`،
  revision واحد، healthy و`RestartCount=0`.
- health gate نجح؛ marketing/staff/owner/portal كلها HTTP 200، والمسار
  المحمي بلا توثيق 401؛ DB/Redis سليمان وlog scan للخدمات الثلاث نظيف.

## 7. التسليم وUAT المتبقي

- دليل القبول: `docs/UAT_REL15_OWNER_STAFF_AR.md`.
- دليل السوبر أدمن: `manual/01-دليل-السوبر-أدمن.md` وPDF المولد.
- دليل الموظفين: `manual/02-دليل-الموظفين-والتدريب.md` وPDF المولد.
- قالب الأسماء: `docs/templates/REL15_STAFF_ROSTER_TEMPLATE.xlsx`؛ ممنوع وضع
  password/OTP/recovery code بداخله.
- القبول التقني مكتمل. لا يُعلن Go تشغيليًا حتى يجرب Mohamed مع المالك
  وممثلي accountant/cashier/HR/manager/timeshare على البيانات الحقيقية.

## 8. Rollback

استخدم manifest المذكور أعلاه لإعادة tags السابقة، ثم أعد إنشاء backend،
worker/beat، Staff/Owner، وNginx بالترتيب نفسه. migration البريد تضيف unique
index وتحوّل البريد إلى lowercase؛ downgrade يسقط index فقط. لا تستعد DB
إلا بعد إثبات فساد بيانات؛ التطبيق السابق متوافق مع البريد lowercase.

ملاحظة خادم غير مرتبطة: `systemctl --failed` يحتوي خدمة
`wegodivers-healthcheck.service` تخص مشروعًا آخر؛ health gate الخاص بـResort
OS ناجح ولا يجب نسب هذا الفشل إليه.
