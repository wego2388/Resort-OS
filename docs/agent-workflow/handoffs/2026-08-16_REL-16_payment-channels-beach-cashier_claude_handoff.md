# Handoff — REL-16: Payment Collection Channels + Beach Cashier Hardening

**التاريخ:** 2026-08-16
**Branch:** `codex/rel-15-auth-ops-readiness`
**Implementation commit:** `4b08698`
**Docs/release commit (deployed):** `43eae4c`
**Alembic:** `a7b3f2c8e9d1 (head)` — additive, single head, downgrade rehearsed
**Status:** DEPLOYED / VERIFIED — see §10 below

## 10. سجل النشر على VPS (2026-08-16)

- **Release commit:** `43eae4cac3a50feb44308d5482e7ba77cafb74a2`
- **Release directory:** `/opt/resort-os-releases/43eae4cac3a50feb44308d5482e7ba77cafb74a2`
  (`/opt/resort-os-current` يشاور عليه الآن)
- **Release archive SHA-256:**
  `fda0d944e11c7c499bdc9959f1dd9f9117e023cb17bf4f7309877126763474a8`
  (اتحقق منه محليًا وعلى الـVPS، متطابق)
- **Active release قبل النشر:** `df27697d53a7ec93a10ed2f8898945ecb4a434a6`
- **DB backup قبل الـmigration:**
  `/opt/resort-os-releases/df27697d53a7ec93a10ed2f8898945ecb4a434a6/backups/resort_os_20260816_052337.dump`
  (744K، اتحقق `pg_restore --list` قرأه صح — 1537 TOC entries)
- **Rollback images manifest:**
  `/var/backups/resort-os/source-releases/43eae4cac3a50feb44308d5482e7ba77cafb74a2-rollback-images.txt`
  (backend/celery-worker/celery-beat/el-kheima/owner/marketing-site/nginx كلهم
  متعلّمين `pre-43eae4c...`)
- **Migration:** `e2f3a4b5c6d7 -> a7b3f2c8e9d1` نجحت بلا أخطاء؛ `alembic current`
  بعدها = `a7b3f2c8e9d1 (head)`. الـbackfill أنشأ 3 قنوات فعلية للفرع
  الوحيد (CASH→1100، CARD→1120، WALLET→1130)، كلهم `is_default=true`
  `is_active=true` — اتأكد بـSQL مباشر بعد الترحيل.
- **الاستبدال:** backend → celery_worker+celery_beat → el_kheima+owner →
  nginx (force-recreate)، بالترتيب المطلوب بالظبط. Postgres/Redis
  ماتلمسوش. RestartCount=0 على الستة كلهم، صورة/revision متطابقين
  (`org.opencontainers.image.revision` = `43eae4c...` على backend/worker/beat).
- **القبول بعد النشر:** الأربع دومينز (`elkheima.com`, `www.`, `app.`,
  `owner.`) بترجع 200 من برّه الخادم؛ `/health` نظيف (DB/Redis latency
  طبيعية)؛ TLS SAN يغطي الأربعة لحد 2026-11-05؛ منافذ 5436/6381 مقفولة من
  برّه (اتأكد فعليًا من الإنترنت مش من جوه الخادم)؛ صفر traceback/critical
  جديد في لوجات backend/celery/nginx بعد الاستبدال.
- **Smoke tests حقيقية (بدون أي معاملة مالية وهمية)**: نداء Python
  read-only جوه container الـbackend الحيّ (rollback بعد كل حاجة، صفر
  كتابة) أكّد: `resolve_tender_channel` بيرجّع الحساب/اللقطة الصح لكل من
  cash/card/wallet مطابقين للـbackfill بالظبط؛ `beach.capacity_max` غير
  مُعرَّف بعد فيرجع fallback 200 صح (القرار التشغيلي المتبقي، راجع تحت).
  نداءات HTTP حقيقية غير مصادَق عليها عبر `app.elkheima.com` الحقيقي
  أكّدت المسارات الجديدة مسجّلة ومحمية (401 مش 404): `/finance/payment-channels`،
  `/beach/sell-cart`، `/beach/inventory`.
- **Health gate الرسمي**: `resort-os-healthcheck.service` — `RESORT_HEALTHCHECK_OK
  passes=16`.
- **Rollback point**: لو محتاج تراجع — retag صور `resort-os-rollback/*:pre-43eae4c...`
  (المانفست فوق)، استبدال بنفس الترتيب المحكوم في §5.E من `DEPLOYMENT.md`،
  إعادة تشغيل كل فحوصات health/TLS/DB/logs. الـmigration إضافية بحتة
  (downgrade نظيف اتأكد منه محليًا قبل النشر) — رجوع التطبيق فقط لا يبرر
  استرجاع الداتابيز.
- **قنوات التحصيل الحقيقية — اتضافت بعد النشر (2026-08-16، بتأكيد
  Mohamed المباشر)**: عبر نفس service layer المُتحقّق منه (مش SQL خام)
  على الإنتاج مباشرة:
  - `VISA_CIB` (id=4، method=card، GL=1120 "وسيط تحصيلات الكارت"،
    `is_default=true`) — فيزا وماستركارد بيعدّوا على نفس الجهاز/الحساب
    حسب تأكيد Mohamed، فمفيش قناة Mastercard منفصلة.
  - `VODAFONE_CASH` (id=5، `is_default=true`)، `ORANGE_CASH` (id=6)،
    `ETISALAT_CASH` (id=7)، `INSTAPAY` (id=8) — الأربعة method=wallet،
    GL=1130 "وسيط تحصيلات إلكترونية" (حساب واحد مشترك حسب طلب Mohamed
    الصريح — قنوات منفصلة للعرض/التقارير بس، مش حسابات منفصلة).
  - القناتين العامتين القديمتين `CARD`/`WALLET` اتعطّلوا
    (`is_active=false`)، مش محذوفتين.
  - اتأكد بنداء حي حقيقي: `resolve_tender_channel` بيرجّع الآن
    `VISA_CIB`/`VODAFONE_CASH` كـdefault لكل من card/wallet.
  - **مؤجَّل صراحةً (task #12 في نظام المهام)**: مفيش أي `bank_accounts`
    حقيقية مسجّلة في النظام لسه (الجدول فاضي بالكامل) — الـ4 قنوات
    الجديدة `bank_account_id=NULL`. البيع والمحاسبة شغالين صح 100%
    بدونه؛ الأثر الوحيد إن مطابقة كشف الحساب البنكي الأوتوماتيكية مش
    هتشتغل لحد ما Mohamed يدّي اسم بنك ورقم حساب CIB الحقيقي (للفيزا)
    وحساب المحفظة، وقتها هتتربط عبر `PATCH /finance/payment-channels/{id}`.
- **القرار التشغيلي المتبقي**: تُدخل رقم `beach.capacity_max` الحقيقي
  في الإعدادات — لحد كده الشاشة شغالة بـfallback 200. زائد الحسابات
  البنكية الحقيقية المذكورة فوق (اختياري).

## 1. الخلفية

استكملت شغل Codex غير المكتمل (نموذج `PaymentChannel` وحقول snapshot جزئية
بلا migration/API/UI) وأضفت النظام كامل: قنوات تحصيل حقيقية مخزّنة في
الداتابيز، branch-scoped، لكل واحدة حساب GL إلزامي وحساب بنكي اختياري،
مربوطة بالشاطئ والدايننج والتقارير المحاسبية، زائد تحسين سعة الشاطئ
وتحصين كاشير الشاطئ المطلوبين في نفس الدفعة.

## 2. أولًا: سعة الشاطئ (تأكيد عمل Codex + إغلاق فجوات صغيرة)

- `beach.capacity_max` مصدر السعة الحقيقي فعليًا (كان عمل Codex شبه مكتمل
  ومُختبر — 186 اختبار). فحصت المنطق بالكامل: قبول عدد صحيح موجب فقط
  (`app/resort_os/beach_engine.py::parse_beach_capacity_max`)، حد أعلى آمن
  100,000، رفض 400 عند القيمة غير الصحيحة عبر `core.services.upsert_setting`،
  fallback 200 فقط عند غياب الإعداد، اليوم التشغيلي بتوقيت القاهرة، تحديث
  آمن لليوم الحالي دون لمس الأيام الماضية.
- **أصلحت اختبارين** كانا يستخدمان `date.today()` الخام بدل business date
  (ممكن يفشلوا قرب منتصف ليل UTC بينما القاهرة في يوم تاني) —
  `test_new_day_uses_branch_capacity_setting` و
  `test_setting_change_updates_today_but_preserves_past_snapshot`.
- **وضّحت في الواجهة** (BeachPOSView/BeachAdminView/BeachLiveDashboardView،
  ar+en) أن الرقم المعروض هو تذاكر الدخول المباعة اليوم، وليس عدد الضيوف
  الموجودين لحظيًا.

## 3. ثانيًا: قنوات التحصيل والحسابات المحاسبية (جديد بالكامل)

### الموديل + الـmigration

- `finance.PaymentChannel` (كان Codex بدأه في `models.py` بلا migration):
  `code` فريد لكل فرع، اسم عربي/إنجليزي، `method` (cash|card|wallet)،
  `gl_account_id` إلزامي، `bank_account_id` اختياري، `is_default`/
  `is_active`/`sort_order`. Unique index جزئي `(branch_id, method)` عند
  `is_default=true` يضمن default واحد فقط.
- Migration إضافية `a7b3f2c8e9d1` (فوق `e2f3a4b5c6d7`، head واحد): تنشئ
  `payment_channels`، تضيف 4 أعمدة snapshot
  (`payment_channel_id/code/name`, `settlement_account_code`) على
  `payments` و`beach_transactions`، وتزرع default واحد لكل (فرع، طريقة)
  **فقط** لو الحساب المطابق (1100 كاش/1120 كارت/1130 محفظة) موجود بالفعل
  ونشط في دليل حسابات الفرع — صفر حسابات مخترعة. اتأكدت فعليًا على
  Postgres حقيقي: upgrade من فارغة، upgrade مع بيانات backfill حقيقية
  (بما فيها تخطي حساب غير نشط بنجاح)، `UNIQUE` الـdefault بيرفض تكرار
  فعليًا، و**downgrade كامل نجح** (drop نظيف لكل الأعمدة/الجدول).

### التحقق (finance.services)

- `create_payment_channel`/`update_payment_channel`: حساب GL لازم يكون
  `active` و`asset` وبنفس الفرع؛ الحساب البنكي (لو موجود) لازم يكون
  `active` وبنفس الفرع؛ قناة `cash` تُرفض لو مربوطة بحساب بنكي؛ تعطيل
  بدل حذف (لا يوجد مسار DELETE في الـAPI أصلًا).
- `resolve_payment_channel(db, branch_id, method, channel_id=None)`: قناة
  محددة صراحةً لازم تكون نشطة وبنفس الفرع/الطريقة؛ بدون تحديد → default
  الفرع؛ فرع بلا أي قنوات لهذه الطريقة → `None` (**legacy fallback** —
  السلوك القديم بدون أي تغيير)؛ فرع عنده قنوات لكن بلا default صالح →
  خطأ صريح (لا ترحيل لحساب عشوائي).
- `payment_channel_snapshot(channel)`: يبني اللقطة التاريخية الأربعة —
  لقطة، مش مرجع حي؛ تعديل القناة بعد البيع مؤكَّد بالاختبار أنه لا يغيّر
  أي حركة قديمة.

### API + شاشة الإدارة

- `POST/GET/PATCH /finance/payment-channels` (`get_finance_user` + فحص
  فرع حقيقي `assert_branch_access`، مش مجرد إخفاء زر). لا يوجد DELETE.
- شاشة جديدة داخل `FinanceView.vue` (تاب "قنوات التحصيل"، ar/en RTL/LTR):
  إضافة/تعديل/تعطيل، اختيار default، اختيار حساب GL وبنكي من قوائم
  حقيقية، رسائل خطأ واضحة.

### الربط الفعلي

- **مشترك بين الشاطئ والدايننج**: نقطة موحّدة جديدة
  `dining.payment_policy.resolve_tender_channel(db, branch_id, method,
  channel_id)` — تحل القناة الحقيقية أولًا، وتسقط لـ
  `resolve_direct_tender_account` القديمة (env-based) فقط لو الفرع بلا
  قنوات. تستخدمها `beach.services` و`dining.services` الاتنين.
- **الشاطئ**: `BeachSellRequest.payment_channel_id` جديد؛ اللقطة تُحفظ على
  `BeachTransaction` و`Payment` معًا؛ الإلغاء (`void_transaction`) يستخدم
  **حساب اللقطة الأصلي** بدل ثابت `1100` — هذا كان **باج حقيقي موثّق
  صراحةً في الكود القديم** ("فجوة غير معدَّلة، خارج النطاق") تم إغلاقه
  فعليًا الآن.
- **الدايننج**: `payment_channel_id` على الدفع المفرد
  (`OrderStatusUpdate`) وعلى كل صف في `SplitBillPayment` — كل صف في
  تقسيم الفاتورة ممكن يستخدم قناة مختلفة. اللقطة تُحفظ في
  `Payment` وفي `DiningSettlement.tender_breakdown` (JSON، نفس الآلية
  الموجودة بالفعل لتفاصيل الـtenders، مفيش أعمدة جديدة على
  `DiningSettlement` نفسه).
- **تقارير الوردية (X/Z)**: `ShiftEndReport.channel_breakdown` جديد —
  تجميع المبيعات حسب القناة الفعلية وقت البيع (لقطة، مش حي)؛ مبيعات
  legacy بلا قناة تظهر تحت اسم الطريقة الخام بدل ما تختفي.
- **مطابقة البنك**: `find_matching_payment_candidates(...,
  bank_account_id=...)` — الـauto-match بيقصر المرشحين على الدفعات اللي
  قناتها مربوطة بنفس الحساب البنكي؛ دفعات legacy (بلا قناة) لسه بتترشح
  عادي (توافق آمن).

## 4. ثالثًا: كاشير الشاطئ

- **Shift مفتوحة إلزامية لأي دفع مباشر** (cash/card/wallet) — نفس قاعدة
  الدايننج بالظبط، عبر `beach.services.NoOpenShiftError` (409
  `NO_OPEN_SHIFT`، نفس الشكل اللي الفرونت إند بيتعرف عليه بالفعل من
  الدايننج). طُبّقت على `/beach/sell`، `/beach/sell-cart`،
  `/beach/reservations/{id}/checkin`، `/beach/locations/{id}/checkin`.
- **سلة atomic حقيقية** — `POST /beach/sell-cart` جديد (`sell_cart`
  service): كل الأصناف تترحّل في transaction واحدة، إما كلها تنجح أو ولا
  واحد منهم؛ idempotency على مستوى السلة كلها (`cart_local_id`، بيبني
  `local_id` لكل صنف منه، بيعيد نفس النتيجة عند retry). الفرونت إند
  (`BeachPOSView.vue`) بيستخدمه الآن للمسار الأونلاين بدل الحلقة القديمة
  اللي كانت بتبعت طلب منفصل لكل صنف (بيع جزئي حقيقي كان ممكن يحصل). طابور
  الأوفلاين (`useOfflineQueue`) لسه per-item — قرار موثّق: إعادة هندسة
  الطابور نفسه خارج نطاق هذه الدفعة.
- **⚠️ باج حقيقي اتكشف واتصلح أثناء بناء السلة الـatomic**: كل قيد
  محاسبي في الشاطئ (وفي الدايننج، غير متأثر) كان بينادي
  `post_taxed_sale_journal`/`reverse_taxed_sale_journal` بالإعداد
  الافتراضي `commit_cost_centers=True`، اللي بيعمل **commit ضمني** وسط
  أي عملية بيع (لبناء مراكز التكلفة الافتراضية أول مرة). ده كان معناه إن
  **كل بيع شاطئ من الأساس** كان بيقفل الـtransaction بدري من غير قصد —
  ظهر فعليًا بس لما بنيت السلة الـatomic وأول صنف نجح فعليًا اتثبّت في
  الداتابيز قبل ما نوصل للصنف التاني، فرفض صنف لاحق ما قدرش يرجع الصنف
  الناجح. الحل: تمرير `commit_cost_centers=False` صراحةً في كل نداءات
  الشاطئ الأربعة (بيع/void، مباشر/فوليو) — نفس النمط اللي الدايننج
  بيستخدمه فعليًا من الأول (Gate 1B). مُثبَت باختبار حي كان بيفشل قبل
  الإصلاح وبيعدي بعده.
- **باج race حقيقي تاني اتصلح**: `beach.crud.get_or_create_inventory`
  (أول صف سعة يومي) كان check-then-insert بسيط بلا حماية — أول بيعتين في
  نفس اللحظة بالظبط (زي أول كاشير يفتح الشاشة الصبح) كانوا ممكن الاتنين
  يحاولوا INSERT، والتاني يرمي `IntegrityError` خام (500) بدل رجوع صف
  اليوم الفعلي. الحل: `SAVEPOINT` (`db.begin_nested()`) حوالين الـINSERT
  بس — لو اتصادم، رجوع للـSAVEPOINT فقط (مش `db.rollback()` الكامل، اللي
  كان هيمسح أي تعديلات تانية غير ملتزمة في نفس الـtransaction الأكبر، زي
  أصناف سابقة في سلة atomic). مُثبَت باختبار monkeypatch يحاكي TOCTOU.
- **حد كمية** — `BeachSellRequest.quantity`/`BeachCartLineItem.quantity`
  بقى `le=100` (كان بلا حد أعلى خالص).
- **واجهة void حقيقية** — زر إلغاء جديد في `BeachAdminView.vue` (تاب
  المعاملات، مقيّد لمدير+ في الواجهة، والصلاحية الحقيقية Backend عبر
  `require_permission("beach.void_transaction", min_role_level=60)`
  الموجودة بالفعل) بمودال يطلب سبب (3 أحرف على الأقل) قبل الإرسال.
- **استلام كاش/فكة بالجنيه** — `BeachPOSView.vue` كان عنده حساب فكة
  بالعملة الأجنبية بس، مفيش أي حقل استلام/فكة للجنيه العادي خالص. أُضيف
  باستخدام وحدات صحيحة (قروش، `money.ts` المشتركة من الدايننج) بدل float.
- **أصلحت باج حقيقي في lookup الحساب الآجل** (شاطئ ودايننج الاتنين):
  تعديل رقم الموظف بعد بحث ناجح كان بيسيب `creditAccount` القديم محمّل
  من غير مسح — لو الكاشير صحّح غلطة إملائية في الرقم بس نسي يضغط "بحث"
  تاني، البيع كان ممكن يترحّل على حساب موظف تاني تمامًا. أُضيف `watch`
  يمسح الحساب المحمّل فورًا عند أي تغيير في الرقم الخام.

## 5. رابعًا: كاشير الدايننج

- قناة التحصيل على الدفع المفرد وعلى كل صف split (تفصيل كامل في §3).
- **أصلحت باج ترجمة حقيقي**: `paymentMethodLabel()` في
  `DiningOrderDetailModal.vue` كانت بتقارن `method === 'split'` حرفيًا،
  لكن القيمة المخزّنة فعليًا هي `"split:cash,card"` (تفصيل الطرق
  الحقيقية) — المطابقة كانت بتفشل والنص الخام كان بيظهر للمستخدم زي ما
  هو (بالظبط الباج اللي طلب Mohamed إصلاحه). أُصلح ليحلّل البادئة
  ويترجم كل طريقة داخلها.
- الحساب الآجل: نفس إصلاح مسح lookup عند تغيير الرقم (§4).

## 6. مؤجَّل عمدًا (قرار نطاق موثّق، مش نسيان)

- إعادة هندسة طابور الأوفلاين (`useOfflineQueue`) ليكون cart-atomic بدل
  per-item — الطابور الحالي نظام دقيق ومُختبر، وإعادة هندسته تحتاج دفعة
  منفصلة مركّزة.
- عرض قناة التحصيل داخل الإيصال الحراري نفسه وتفاصيل الفاتورة في شاشة
  الإدارة — الـبيانات محفوظة بالكامل (اللقطة موجودة في `Payment`/
  `tender_breakdown`)، العرض البصري في PDF/الفاتورة لسه غير مربوط.
- إعادة مراجعة شاملة لواجهة الحجوزات (reservations) — لم تُلمس في هذه
  الدفعة؛ الـAPI الحالي كافٍ لعمل الاختبارات الموجودة.
- فصل صريح لـ provenance بين manual surge وauto surge — لم يُلمس (خارج
  النطاق المتفق عليه لهذه الدفعة تحديدًا، السلوك الحالي كما كان).
- سياسة خصم مخزون الطعام — لم تُغيَّر (لا قرار مالك موجود في التوثيق).

## 7. الاختبارات

ملفات جديدة: `test_beach_payment_channels.py` (12، شامل باج الـcommit
الضمني وباج الـrace)، `test_dining_payment_channels.py` (3)،
`test_finance_payment_channels_http.py` (18، شامل مطابقة البنك حسب
القناة). تعديل: `test_beach.py`/`test_beach_http.py`/
`test_beach_engine.py` لدعم الـshift guard الجديد وbusiness-date.

- Backend `pytest tests/ -v`: **2850 passed, 68 skipped, صفر failure**
  (2918 collected).
- `alembic heads`: `a7b3f2c8e9d1 (head)` — واحد فقط.
- `pnpm run type-check:all`: نظيف (el-kheima + owner).
- `pnpm --filter el-kheima test:frontend`: **106/106** (i18n parity 6377
  مفتاح، صفر فارغ).
- `pnpm --filter el-kheima test:e2e:mock`: **8/8**.
- `pnpm --filter owner test:e2e`: **12/12**.
- `pnpm run build:all`: نظيف (el-kheima + owner).
- `docker compose config` (dev + prod): نظيف.
- `bash scripts/agent-check.sh`: PASS.
- `git diff --check`: نظيف.

## 8. المخاطر والتراجع

- Migration إضافية بالكامل (create table + add columns + backfill
  محافظ)، `downgrade()` مُختبر فعليًا ونظيف. لا تعديل على migration
  مطبّقة، لا حذف بيانات.
- شرط الوردية المفتوحة الجديد **يغيّر سلوكًا حقيقيًا**: أي كاشير بيحاول
  بيع مباشر بلا وردية مفتوحة هيترفض 409 بدل ما ينجح بصمت بلا نسبة وردية
  (كان السلوك القديم). التأثير مقصود ومطابق للطلب الصريح، لكنه blast
  radius حقيقي على أي مسار قديم كان بيعتمد على البيع بلا وردية — روجعت
  كل نقاط الدخول الأربعة المذكورة في §4.
- Rollback تطبيقي: نفس آلية DEPLOYMENT.md §7 (retag rollback images،
  استبدال متحكَّم، لا استرجاع DB إلا بعد إثبات تلف فعلي). التوافق مع DB
  الحالية كامل (migration إضافية بحتة)، فـrollback كودي فقط كافٍ عند
  الحاجة.

## 9. القرار التشغيلي المتبقي

القبول التقني لهذه الحزمة مكتمل بالكامل حسب البوابات أعلاه. مفيش قرار
مالي أو بيانات حقيقية اتغيّرت — قنوات التحصيل نفسها لسه محتاجة Mohamed
يدخل شاشة "قنوات التحصيل" في `/admin/finance` ويضيف القنوات الحقيقية
(Visa CIB، Vodafone Cash...) بعد النشر؛ لحد ما يحصل كده، كل الفروع
بتشتغل بمسار legacy القديم تلقائيًا بلا أي انقطاع تشغيلي.
