# حالة المشروع الحالية — El Kheima Beach Resort OS

**آخر تحديث:** 2026-08-30 — **نشر REL-23 + REL-24 على الإنتاج** (commit
`0e55ac038a8603d2fa4f24e5353a2c9a0288fb45`) على سيرفر VPS جديد
(`31.97.193.77`، بعد ما الـDNS الحقيقي اتحوّل عليه). Deploy كامل باتباع
`DEPLOYMENT.md` §5 حرفيًا (release artifact + rollback point + preflight +
استبدال تدريجي بالترتيب backend→celery→frontends→nginx، health check حقيقي
بعد كل خطوة). اكتشاف حقيقي أثناء التنفيذ: TLS مكانتش مُصدرة خالص على هذا
السيرفر الجديد (فجوة إعداد سابقة، مش تراجع سببه الـdeploy) — اتصلحت بإصدار
شهادة Let's Encrypt حقيقية أول مرة (الأربع نطاقات) + تركيب automation
التجديد الرسمية للمشروع (كانت غير مثبتة خالص على السيرفر ده). كل بنود
post-release acceptance (§6) اتحققت: alembic عند head الصحيح، صور backend/
celery متطابقة IDs وrevision label، HTTPS 200 على الأربع نطاقات، TLS SAN
صحيح، لوجات نظيفة. تفاصيل كاملة:
`docs/agent-workflow/handoffs/2026-08-30_REL-23-REL-24_production-deploy_claude_handoff.md`

**السابق:** 2026-08-30 — REL-24: باقي الـ11 finding من مراجعة Codex
المستقلة (H-01 حتى M-04) اتنفّذوا كاملين بعد موافقة محمد الصريحة على
الاستمرار من غير توقف. أهمها: إلغاء حجز PMS وهو الضيف لسه نازل (كان
بيرجّع الغرفة "متاحة" وهي مشغولة فعليًا)، تسوية عقود B2B غير ذرية
(ممكن تحصيل مزدوج)، ترتيب أقفال معكوس في تحصيل/إلغاء عقود الملكية
الجزئية، استلام أمر شراء بلا قفل ولا تجميع تكرار الصنف، فجوات عزل فرع
متبقية في HR وAnalytics (~15 endpoint إضافي)، وعاء تأمين اجتماعي أكبر
من الراتب الأساسي (زائد اكتشاف فجوة أعمق: قيد الرواتب المجمّع كان بلا
فحص توازن خالص)، عقود ملكية جزئية ملغاة تفضل في تقارير التحصيل،
إدارة PIN بلا فحص فرع/مستوى نسبي، استبيان رضا قابل للتكرار بلا حد
(migration جديدة + rate limit)، وشاشة أسعار صرف معطّلة في الإنتاج
(مسار API ناقص البادئة). 16 اختبار انحدار جديد، `pytest tests/ -v`
أخضر بالكامل، فرونت إند نظيف (type-check + i18n + vitest). **منشور ومتحقق
فعليًا على الإنتاج الآن (راجع سجل النشر أعلاه، 2026-08-30).** تفاصيل كاملة:
`docs/agent-workflow/handoffs/2026-08-30_REL-24_codex-review-H01-M04_claude_handoff.md`

**السابق:** 2026-08-30 — REL-23: نفس مراجعة Codex، الدفعة الأولى بس
(C-01 — عزل الفروع في Finance، ~30 endpoint). تفاصيل كاملة:
`docs/agent-workflow/handoffs/2026-08-30_REL-23_codex-review-C01-finance-branch-isolation_claude_handoff.md`

**السابق:** 2026-08-29 — REL-22: مراجعة شاملة نهائية قبل التشغيل
الحقيقي (طلب محمد صراحةً) — 8 باجات حقيقية اتكشفت واتصلحت عبر 6
موديولات (تسريب IDOR منهجي في HR وFinance عبر ~26 endpoint، راتب صافي
ممكن يروح سالب، حراس حالة طلب مُرتجَع ناقصة في Dining، أقساط عقود
ملغاة بتتعلّم "متأخرة" للأبد في Timeshare، قفل صفوف ناقص في PMS، تحقق
ناقص في استلام أوامر شراء بالمخزون). كل التستات الخلفية عدّت 100%
والفرونت إند نظيف بالكامل. **الكود جاهز ومُختبَر محليًا — لسه محتاج
commit/push/deploy كخطوة منفصلة.** تفاصيل كاملة:
`docs/agent-workflow/handoffs/2026-08-29_REL-22_pre-launch-comprehensive-audit_claude_handoff.md`

**السابق:** 2026-08-25 — REL-21: تدقيق إنتاج شامل بناءً على طلب
محمد الصريح قبل النقل لـVPS جديد (Hostinger) — حساب B2B مفقود (1165)
اتضاف + 495,000 ج فوترة شهرية اتترحّلت، وباج نظامي حقيقي في تسجيل
موديلات SQLAlchemy جوه Celery worker (كان بيوقف مهمة الملكية الجزئية
اليومية، 18 قسط متأخر عالقين) اتكشف واتصلح جذريًا + اختبار انحدار
حقيقي، وuploads volume دائم اتضاف. منشور ومتحقق فعليًا على الـVPS
(release commit `afb8ce6`؛ صفر migration جديدة — تصحيح بيانات فقط).

## REL-21 — تدقيق إنتاج شامل + إصلاحات تشغيلية (2026-08-25) — DEPLOYED

- محمد بعت تقرير تدقيق إنتاج خارجي (4 مشاكل: فوترة B2B فاشلة لحساب
  1165 مفقود، مهمة الملكية الجزئية اليومية فاشلة بباج SQLAlchemy،
  مفيش نسخ احتياطي خارج السيرفر، مجلد رفع الصور بدون volume دائم)
  وطلب صراحةً الإصلاح الكامل قبل نقل المشروع لسيرفر جديد نظيف.
- **حساب 1165**: أُدخل مباشرة على قاعدة بيانات الإنتاج (فجوة بنيوية
  معروفة — `_seed_chart_of_accounts` ممنوعة من الشغل على production،
  فحسابات جديدة في الكود محتاجة إدخال يدوي على إنتاج موجود من قبل).
  مهمة الفوترة الشهرية اتشغّلت يدويًا بعدها — 3 قيود حقيقية (495,000 ج
  إجمالي، عقود HIST/Panorama/Shsrm klev).
- **باج نظامي في `app/tasks/__init__.py`**: عملية Celery worker
  الحقيقية لا تستورد `app.main` خالص (تخفيف startup)، فأي موديل عنده
  `ForeignKey` حقيقي يفضل غير مسجّل في `Base.metadata` لحد أول task
  يلمسه — نفس فخ `alembic/env.py` الموثّق في CLAUDE.md §13 بند ❹-ب.
  اتصلح باستيراد صريح لكل الـ16 موديول + `users` قبل أي تسجيل تلقائي.
  اتأكّد بإعادة إنتاج حقيقية (مش افتراض) عبر `.delay()` الفعلي، مش
  استيراد Python عادي، واختبار انحدار جديد اتأكّد إنه فعلاً حسّاس
  للباج (فشل لما الإصلاح اتعطّل مؤقتًا، نجح بعد إرجاعه).
- **uploads volume**: `resort_uploads` named volume جديد في
  `docker-compose.prod.yml`، مربوط بـ`/app/uploads` — صفر خسارة بيانات
  حقيقية (مفيش ملفات مرفوعة وقت الإصلاح).
- Backend `pytest -v` + اختبار انحدار جديد
  (`test_tasks_package_registers_models.py`)، `alembic heads` = head
  واحد. النشر: نفس الـrunbook الكامل (release artifact + checksum،
  rollback tags، نسخة احتياطية + `pg_restore --list`، بناء الصور،
  استبدال متحكَّم فيه بترتيب التبعية، health gate الرسمي `passes=16`
  مؤكَّد من سجل systemd الفعلي قبل وبعد النشر). تفاصيل كاملة:
  `docs/agent-workflow/handoffs/2026-08-25_REL-21_production-audit-ops-fixes_claude_handoff.md`
- **معلّق**: النسخ الاحتياطي خارج السيرفر (offsite) محتاج قرار محمد
  لمزود التخزين السحابي وبياناته — الآلية جاهزة بالكامل في الكود.

**السابق:** 2026-08-23 — REL-20: عقود B2B الشهرية (استبدال كامل
لنظام "سعر لكل ضيف × حصة يومية" القديم) + تحسينات شاملة لكاشير الشاطئ
والدايننج (بوابة الطاولة الإجبارية، أمان السلة، تحمّل انقطاع النت)،
منشور ومتحقق فعليًا على الـVPS (release commit `5dbb4f4`؛ migration
واحدة حقيقية).

## REL-20 — عقود B2B شهرية + تحسينات الكاشير (2026-08-23) — DEPLOYED

- Mohamed شرح إن نظام عقود الفنادق الشريكة الحقيقي مختلف عن الكود:
  مبلغ شهري ثابت مقابل حد أقصى استرشادي (تخطّيه مسموح صراحةً)، مش سعر
  لكل ضيف. `B2BContract` اتعمله rewrite كامل (`monthly_fee`/
  `monthly_guest_cap` بدل `daily_quota`/`entry_price`/`towel_price`)،
  `B2BContractMonth` جديد للفوترة الشهرية الآلية (Celery يومي، قيد
  حقيقي Dr.1165/Cr.4300)، التسوية بقت بترحّل قيد عكسي حقيقي بدل علم
  بدون أثر. حساب `1165` (ذمم فنادق شريكة) جديد. Migration `45aabf472620`
  (إضافي/backfill بالكامل، صفر فقدان بيانات). باج حقيقي اتصلح: إلغاء
  تشيك-إن B2B كان هيكسر (`void_transaction` يتصادم مع حارس رفض القيد
  الصفري).
- بعدها، مراجعة شاملة لكاشير الشاطئ (`BeachPOSView.vue`): شريط "آخر
  العمليات" (إعادة طباعة لأي كاشير، إلغاء بـPIN مدير)، اختصارات لوحة
  مفاتيح + إضافة سريعة لعدد ضيوف الفنادق، إدخال كاش بأزرار جاهزة، رسم
  "خدمة" جديد لدخول مأكولات خارجية (٥٠ ج افتراضي، قابل للتعديل).
- ومراجعة شاملة للكاشير الموحّد (`UnifiedPOSView.vue`): إزالة بوابة كانت
  بتجبر الكاشير يفتح طاولة (واسم ضيف إجباري) قبل ما يشوف اختيارات نوع
  الطلب خالص — حتى لو تيك أواي/توصيل/خدمة غرف. أمان السلة (حذف صنف
  واحد بدون تأكيد على زرار ٤٠px بقى ٤٨px + تأكيد فعلي). إصلاح انقطاع
  النت: المنيو/الطاولات بقى آخر رد ناجح بيتخزّن محليًا (localStorage)
  ويرجع تلقائي بدل ما يفضى، تحديث فوري لحظة رجوع الاتصال.
- Backend `pytest -v` كامل → 2960 اجتازوا (+4 اختبارات رسم الخدمة)، صفر
  فشل. Frontend `type-check:all`/`test:frontend` (106/106)/`test:e2e:mock`
  (8/8)/`test:e2e` owner (12/12)/`build:all` نظاف. النشر: backend/celery
  worker+beat/el_kheima/owner كلهم اتبنوا واتستبدلوا، health gate الرسمي
  `passes=16`. تفاصيل كاملة:
  `docs/agent-workflow/handoffs/2026-08-23_REL-20_b2b-monthly-fee-pos-overhaul_claude_handoff.md`

**السابق:** 2026-08-20 — REL-19: إصلاح باج بيع مكرر حقيقي في كاشير
الشاطئ (مسار البيع الأوفلاين الجزئي)، اتكشف أثناء تجربة Mohamed الحية
على الإنتاج وطلبه المباشر بمراجعة الكاشيرات، منشور ومتحقق فعليًا على
الـVPS (release commit `330cc45`؛ `el_kheima` بس، مفيش migration).

## REL-19 — إصلاح بيع مكرر في كاشير الشاطئ (2026-08-20) — DEPLOYED

- Mohamed كان بيجرّب كاشير الدايننج والشاطئ حيًا وطلب مراجعة استباقية
  للمشاكل المحتملة. مراجعة كود منهجية (fork منفصل، مش جزء من دفعة
  REL-18 المحاسبية اللي كانت شغالة في نفس الوقت) كشفت باج حقيقي واحد:
  `BeachPOSView.vue`'s مسار البيع الأوفلاين الجزئي (نداء منفصل لكل صنف
  في السلة، عكس المسار الأونلاين الذري) كان بيبعت كل صنف من غير
  `local_id` — لو صنف نجح وصنف بعده فشل (مخزون خلص)، الحلقة كانت
  بتوقف قبل `clearCart()` فالسلة تفضل عارضة كل الكميات، ولو الكاشير
  ضغط "إتمام البيع" تاني، الصنف اللي نجح فعلاً كان بيتباع مرتين.
  **Release commit:** `330cc454b2b8488f7fca1e968aec0b6cde3dc075`.
- الإصلاح فرونت إند بحت: مفتاح idempotency ثابت لكل صنف
  (`${saleLocalId}:${cartKey}`، نفس نمط `cart_local_id` بتاع المسار
  الأونلاين) بيتبعت كـ`local_id` — آلية dedup الباك إند
  (`services.sell_ticket`) كانت موجودة ومُختبَرة بالفعل بس مش مستخدمة
  في المسار ده. كل صنف نجح بيتشال من السلة فورًا بدل ما يفضل معروض
  كمعلّق. اختبار backend جديد بيحاكي السيناريو بالتحديد (صنف ناجح +
  صنف فاشل + إعادة محاولة).
- كاشير الدايننج اتراجع في نفس المراجعة ولوحظ سليم بالكامل (مسار البيع
  فيه عملية ذرية واحدة أصلاً، مفيهوش نفس الفئة من الباج).
- Backend `pytest -v` كامل → 2966 اجتازوا (زيادة واحد عن آخر مرة —
  الاختبار الجديد)، صفر فشل. Frontend `type-check:all`/`test:frontend`
  (106/106)/`build:all` نظاف. النشر: `el_kheima` بس اتبنى واتستبدل
  (backend/celery/owner متلمسوش خالص — كودهم متغيّرش صفريًا)، health
  gate الرسمي `passes=16`. تفاصيل كاملة:
  `docs/agent-workflow/handoffs/2026-08-20_REL-19_beach-pos-offline-double-sell-fix_claude_handoff.md`

**السابق:** 2026-08-20 — REL-18: كشف حساب، حد موافقة المصروفات، تصدير
PDF/Excel للتقارير المالية، تقرير أعمار الديون، الإقفال السنوي — زائد
إعادة تنظيم شاشة `FinanceView.vue` كاملة في 4 مجموعات منطقية، منشور
ومتحقق فعليًا على الـVPS (release commit `9504ae3`؛ migration واحدة
إضافية: `accounting_year_closes`).

## REL-18 — كشف حساب، حد موافقة، تصدير تقارير، أعمار ديون، إقفال سنوي (2026-08-20) — DEPLOYED

- بعد دفعة REL-17 المحاسبية، سأل Mohamed هل ناقص المحاسب أي حاجة تخص
  شغله — فحص شامل حدّد 5 فجوات حقيقية، Mohamed اختار تنفيذها كلها فورًا
  زائد طلب صريح تاني: تنظيم شاشة المحاسبة "زي برنامج محاسبي حقيقي".
  **Release commit:** `9504ae3d5e9a263757c618b2d36b48db94d8c3f7`.
- Backend (migration واحدة، `accounting_year_closes`): كشف حساب
  (`GET /finance/accounts/{id}/ledger`، رصيد متحرك)، حد موافقة مصروفات
  (`EXPENSE_APPROVAL_THRESHOLD`، PIN مدير+ عبر `policy_engine`،
  `min_approver_level=80` عمدًا أعلى من حد تسجيل المصروف العادي عشان
  الحد يبقى فاعل مش no-op)، 6 endpoints تصدير PDF/Excel (ميزان
  المراجعة/قائمة الدخل/الميزانية)، تقرير أعمار الديون (فوليوهات مفتوحة +
  أوامر شراء/مصروفات آجلة، مبوّب 0-30/31-60/61-90/90+)، وإقفال سنة
  محاسبية (`POST /finance/periods/{year}/close-year`، `min_role_level=80`
  — يرحّل صافي الربح لحساب 3200 عبر `crud.create_journal_entry` مباشرة
  متجاوزًا `validate_period_open` لأن ديسمبر لازم يكون مقفول أصلاً
  كشرط مسبق).
- Frontend: `FinanceView.vue` بقت شريط تابات بمستويين — 4 مجموعات
  (العمليات اليومية / الحسابات والدفتر / التقارير المالية / إعدادات
  متقدمة) بدل 18 تاب مسطّح. صفوف جدول الحسابات بقت قابلة للضغط تفتح
  modal كشف حساب. سند المصروفات: تدفق موافقة PIN تلقائي (بيتبعت عادي،
  ولو السيرفر رفضه برسالة الموافقة تحديدًا بيفتح `PinGuardModal`
  `min-level=80` ويعيد المحاولة) — الفرونت إند ماعندوش نسخة من قيمة
  الحد نفسها. تاب الفترات: شبكة 12 شهر (حالة مفتوح/مقفول من غياب/وجود
  صف `AccountingPeriod`)، زرار إقفال شهر لكل شهر، وزرار "إقفال السنة"
  لمدير+ فقط.
- **إصلاح جانبي أثناء التحقق**: حارس تباين لوني موجود
  (`themeContrast.spec.ts`) كشف `dark:text-gray-500` حقيقي في تاب
  الفترات — اتصلح لـ`dark:text-gray-400` زي باقي النصوص الثانوية.
- اتحقق منه فعليًا بتفاعل حي (Playwright ضد dev server، تسجيل دخول
  `manager@resortos.local`): كل التابات الجديدة بتحمّل بيانات حقيقية،
  كشف الحساب بيفتح، زراير PDF/Excel بترجع ملفات حقيقية (260KB PDF مُتحقَّق
  منه عبر curl مباشر)، اختبار API مباشر لحد الموافقة رجّع رسالة الرفض
  المتوقعة بالظبط. Backend `pytest -v` (كامل، مش `-q` — البيئة دي بتخفي
  سطر النتيجة مع `-q`) صفر فشل (2965 اجتازوا، 68 اتخطّوا). Frontend:
  `type-check:all` نظيف، `test:frontend` 106/106، `test:e2e:mock`
  el-kheima 8/8، `test:e2e` owner 12/12، `test:e2e` el-kheima حي 74/74،
  `build:all` نظيف. النشر: `backend`/`celery_worker`/`celery_beat`/
  `el_kheima`/`nginx` اتبنوا واتستبدلوا، health gate الرسمي
  `passes=16`. تفاصيل كاملة:
  `docs/agent-workflow/handoffs/2026-08-20_REL-18_finance-ledger-approval-reports-year-close_claude_handoff.md`
- **مؤجَّل عمدًا برّه نطاق REL-18**: باج حقيقي منفصل اتكشف أثناء مراجعة
  كود كاشير الشاطئ بطلب Mohamed المباشر وهو بيجرّب الكاشيرات حيًا —
  `BeachPOSView.vue`'s مسار البيع الجزئي/أوفلاين ممكن يبيع نفس الصنف
  مرتين لو صنف تاني في نفس السلة فشل بعد نجاح صنف قبله (مفيش idempotency
  key لكل صنف، عكس المسار الأونلاين الذري). قيد الإصلاح منفصل عن الدفعة
  دي.

**السابق:** 2026-08-17 — REL-17c: الضغط على كارت الإيراد/المصروف في
تطبيق المالك بيفتح تفصيل حقيقي بالحساب ثم قيود اليومية، منشور ومتحقق
فعليًا على الـVPS (release commit `b162bbe`؛ مفيش migration).

## REL-17c — تفصيل الإيراد/المصروف بالحساب في تطبيق المالك (2026-08-17) — DEPLOYED

- Mohamed طلب: الضغط على كارت زي "إيراد اليوم"/"مصروفات اليوم" يوريه
  تفاصيل أكتر، مسحوبة من الحسابات نفسها، بطريقة كويسة وذكية.
  **Release commit:** `b162bbed78a0d169c13b59f92d9fa9c1cae75b4a`.
- جانب المصروف كان عنده بنية تحتية جاهزة من قبل ("Phase 8" drill-down في
  `ExpensesScreen.vue`) لكن مالهاش أي اختبار خالص، ومش موصول بكروت
  "الآن"/"الأداء" الرئيسية. جانب الإيراد ملوش أي endpoint تفصيل بالحساب
  خالص.
- Backend إضافي بحت (مفيش migration): `GET /owner/revenue-breakdown`
  (غلاف رفيع فوق `finance.get_income_statement`'s الموجودة أصلاً
  `revenue_lines` — صفر حساب جديد) و`GET /owner/revenue-detail` (نظير
  `expense-detail` على جانب الدائن — الإيراد يزيد بالدائن). 9 اختبار
  جديد يغطي المسارين (كان صفر تغطية للعائلة دي كلها قبل كده).
- Frontend: `MetricCard.vue` بقى قابل للضغط (`clickable` prop، بيتحول
  لـ`<button>` حقيقي)، composable مشترك جديد
  `useAccountBreakdownDrilldown` (مستويين: قائمة حسابات → قيود يومية
  فعلية داخل حساب منها، مع زرار رجوع) — مستخدم في `NowScreen` (فترة =
  اليوم) و`PerformanceScreen` (فترة = أي تاب نشط: اليوم/الأسبوع/الشهر).
  "كاش الأدراج" بيودّي لشاشة `/shifts` بدل drill-down (تفاصيله الحقيقية
  هناك أصلاً).
- اتحقق منه فعليًا بتفاعل حي (Playwright، ضغطات فعلية): كارت → تفصيل
  بالحساب → حساب → قيود يومية فعلية → رجوع → إغلاق، صفر overflow طول
  التسلسل. Backend `pytest -q` صفر فشل (2956 مجمّعة)، `type-check:all`
  نظيف، `test:e2e` owner **12/12**. النشر: `backend`/`celery`/`owner`
  اتبنوا واتستبدلوا (`el_kheima`/`nginx` متلمسوش)، health gate الرسمي
  `passes=16`. تفاصيل كاملة:
  `docs/agent-workflow/handoffs/2026-08-17_REL-17c_owner-app-account-drilldown_claude_handoff.md`

**السابق:** 2026-08-17 — REL-17b: لايت مود كامل + تفضيل حجم نص
(عادي/كبير/أكبر) لتطبيق المالك، منشور ومتحقق فعليًا على الـVPS
(release commit `65a0605`؛ تغيير frontend بحت، مفيش migration).

## REL-17b — لايت مود + نص أوضح لتطبيق المالك (2026-08-17) — DEPLOYED

- Mohamed جرّب تطبيق المالك بنفسه، لاحظ إن الأرقام/النص صغيرة وهو لابس
  نظارة قراءة، وطلب لايت مود كامل — قرار منتج صريح يلغي قرار "dark-first
  فقط" الأصلي في Decision 0004. **Release commit:** `65a06052dbbad5ed`.
- لايت/دارك مود حقيقي بإعادة استخدام كاملة للآلية الموجودة فعلاً في
  el-kheima (`useTheme`/`initTheme`/`<ThemeToggle>` من
  `@resort-os/core`/`@resort-os/ui`) — الألوان `owner-*` في
  `tailwind.config.js` بقت بتتحل من CSS vars (لايت افتراضي، دارك تحت
  `.dark` بنفس القيم الأصلية بالظبط)، فكل الـ~450 استخدام موجود عبر
  الـ17 شاشة بيتلوّن صح تلقائيًا من غير أي تغيير في مكان الاستخدام.
  12 استخدام Tailwind class غامق ثابت (صناديق خطأ/تحذير) اتحوّلوا
  لمكافئهم المعتمد على الـtoken الجديد. باج تباين حقيقي اتصلح: badge
  عداد حرج كان نص أسود على أحمر فاشل WCAG AA مع الأحمر الفاتح الجديد.
- تفضيل حجم نص (عادي/كبير/أكبر) — `useTextScale.ts` جديد بيغيّر جذر حجم
  الخط (17/19/21px) بدل تعديل ~200 Tailwind text-size class فردي، فكل
  نص/رقم في التطبيق بيكبر مع بعض من إعداد واحد.
- **باج حقيقي اتصلح اكتشفه e2e test موجود بالفعل**: ارتفاع النافبار
  السفلي الأدنى الثابت (56px) وpadding المحجوز في `.owner-main` طلعوا
  مش متزامنين لما جذر حجم الخط كبر — اتصلح بتحويل الاتنين لنفس قيمة rem.
- اتحقق منه فعليًا بتفاعل حي (Playwright، ضغط زرار حقيقي، مش build ناجح
  بس): خلفية `.owner-card` اتغيّرت فعليًا `أبيض ↔ #1C1B1A` (اللون
  الأصلي محفوظ حرفيًا)، حجم الخط دار `17→19→21→17px` صح مع حفظ
  `localStorage`، صفر overflow. `type-check:all`/`build:all` نظاف،
  `test:e2e` **12/12** (320-1280px).
- النشر: حاوية `owner` فقط اتبنت واتستبدلت (backend/celery/el_kheima/
  nginx فضلوا زي ما هم — مفيش migration ولا تغيير backend). الـbundle
  المنشور اتأكد إنه نفس hash الـbuild المحلي بالظبط. Health gate
  الرسمي: `passes=16`. تفاصيل كاملة:
  `docs/agent-workflow/handoffs/2026-08-17_REL-17b_owner-app-light-mode-readability_claude_handoff.md`

**السابق:** 2026-08-16 — REL-17: استرداد بيانات دخول الموظفين +
إصلاح إضافة أصناف لطلب دايننج مفتوح + اختيار وحدة زيارة التيم شير +
3 سندات محاسبية حقيقية (قيد يدوي/مصروفات/دفع موردين)، منشور ومتحقق
فعليًا على الـVPS (release commit `3f44a14`؛ Alembic `79d4d53e7109`
فعّال على الإنتاج).

## REL-17 — استرداد الدخول + إصلاحات دايننج/تيم شير + سندات محاسبية (2026-08-16) — DEPLOYED

- **Release commit المنشور فعليًا:** `3f44a14` (فرع
  `codex/rel-15-auth-ops-readiness`)
- **الإنتاج**: `/opt/resort-os-current` → `/opt/resort-os-releases/3f44a14...`؛
  الستة containers (backend/celery_worker/celery_beat/el_kheima/owner/nginx)
  استُبدلوا بالترتيب المحكوم، RestartCount=0، صفر خطأ جديد في اللوجات،
  health gate الرسمي `passes=16`. تفاصيل كاملة في §10 من
  `docs/agent-workflow/handoffs/2026-08-16_REL-17_credential-reset-dining-timeshare-finance-vouchers_claude_handoff.md`.
- **Migration:** `79d4d53e7109` — إضافية بحتة فوق `a7b3f2c8e9d1`، head
  واحد. تُنشئ `expenses` + `supplier_payments`، وتضيف
  `purchase_orders.amount_paid`/`payment_status`.
- **استرداد بيانات دخول الموظفين (SuperAdmin)**: سبب حقيقي — قفل حساب
  المحاسب "يوسف رمضان بخيت" بمحاولات باسورد خاطئة متكررة، ومفيش أداة
  ويب لاسترداد موظف عادي (الأداة الوحيدة كانت CLI مقصورة على
  super_admin/owner). `core.services.reset_staff_credentials` جديدة
  (محمية step-up) — بترفض صراحة أي هدف super_admin/owner (نفس حدود
  `BOOTSTRAP_CREATABLE_ROLES` بالظبط)، بتولّد باسورد مؤقت + enrollment
  token جديد لو الدور محتاج 2FA إجباري، تمسح قفل الحساب، تلغي كل
  refresh tokens وrecovery codes القديمة، وتكتب `AuditLog`. زرار جديد
  في شاشة `/admin/super-admin` لكل صف موظف (مخفي لصفوف
  super_admin/owner).
- **إصلاح كاشير الدايننج — إضافة أصناف لطلب مفتوح**: باج UX حقيقي —
  مفيش طريقة كانت موجودة لإضافة صنف لطلب اتبعت للمطبخ بالفعل غير عمل
  طلب منفصل بالكامل. اتضاف "وضع الإضافة" في `POSCartPanel.vue` (بيعيد
  استخدام نفس شاشة بناء السلة الموجودة، مفيش تكرار لمنطق تصفح المنيو)
  + زرار "➕ إضافة أصناف للفاتورة" في `DiningOrderDetailModal.vue`.
- **التيم شير — خريطة وحدات حقيقية عند تأكيد الزيارة**: قبل كده كان
  تعيين الوحدة تلقائي بالكامل وأعمى (`find_available_unit`) بلا أي
  رؤية للموظف. `GET /timeshare/units/availability` جديد +
  `TimeshareUnitPicker.vue` — شبكة وحدات فعلية قابلة للاختيار في مودالي
  الموافقة/جدولة الزيارة، بيحترم عقود الوحدة الثابتة (يرفض اختيار
  يدوي يخالف العقد) وعقود Family Compound (لسه تلقائي زي ما هو).
- **3 سندات محاسبية حقيقية جديدة** (بعد سؤال Mohamed عن أنواع السندات
  المحاسبية المصرية القياسية):
  1. **سند القيد اليدوي** (`FinanceView.vue`، تاب جديد) — واجهة حقيقية
     أول مرة لـ`POST /finance/journal-entries` الموجود من قبل بلا أي
     شاشة تستخدمه، بميزان مدين/دائن حي قبل الإرسال.
  2. **سند المصروفات المصنّفة** (`finance.Expense` جديد) —
     `POST/GET /finance/expenses`، الفئة = حساب حقيقي من دليل
     الحسابات (مفيش enum موازي)، بيستخدم
     `post_simple_revenue_journal(..., strict=True)` +
     `validate_period_open` صراحة (فعل محاسبي بيبدأه محاسب، مش ترحيل
     تلقائي من نقطة بيع).
  3. **سند دفع الموردين** (`inventory.SupplierPayment` جديد +
     `PurchaseOrder.amount_paid`/`payment_status`) — كان فيه فجوة
     محاسبية حقيقية: استلام أمر شراء بيرحّل Dr.1200/Cr.2200 (ذمم
     دائنة) من الأساس، لكن مفيش أي طريقة كانت موجودة لتسجيل سداد
     الذمة دي أبدًا. `POST /inventory/purchase-orders/{id}/pay` بيقفل
     الذمة (Dr.2200/Cr.حساب التسوية) بنفس نمط `strict=True` +
     `validate_period_open`. شاشة "مستحقات الموردين" جديدة في
     `InventoryView.vue`.
- **باج dark-mode حقيقي اتصلح قبل الديبلوي**: تاب المصروفات الجديد في
  `FinanceView.vue` استخدم `dark:text-gray-500` (تباين منخفض جدًا على
  الخلفية الداكنة) بدل النمط المعتمد `dark:text-gray-400` في باقي
  الملف — اكتشفه test guard موجود بالفعل (`themeContrast.spec.ts`)،
  اتصلح قبل الـcommit.
- **البوابات**: backend `pytest tests/ -q` → صفر فشل (2947 test
  collected)، `agent-check.sh` PASS، `alembic heads` → head واحد
  `79d4d53e7109`، `git diff --check` نظيف. frontend `type-check:all`
  نظيف (el-kheima + owner)، `validate-i18n` نظيف (6445 مفتاح كل لغة،
  صفر ناقص)، `test:frontend` **106/106**، `test:e2e:mock` **8/8**،
  `build:all` نظيف.
- تفاصيل كاملة:
  `docs/agent-workflow/handoffs/2026-08-16_REL-17_credential-reset-dining-timeshare-finance-vouchers_claude_handoff.md`

**السابق:** 2026-08-16 — REL-16: قنوات تحصيل حقيقية (Payment
Channels) + تحصين كاشير الشاطئ، منشور ومتحقق فعليًا على الـVPS
(release commit `43eae4c`؛ Alembic `a7b3f2c8e9d1` فعّال على الإنتاج).

## REL-16 — قنوات التحصيل + تحصين كاشير الشاطئ (2026-08-16) — DEPLOYED

- **Implementation commit:** `4b08698` — **Release commit المنشور فعليًا:**
  `43eae4c` (فرع `codex/rel-15-auth-ops-readiness`)
- **الإنتاج**: `/opt/resort-os-current` → `/opt/resort-os-releases/43eae4c...`؛
  الستة containers (backend/celery_worker/celery_beat/el_kheima/owner/nginx)
  استُبدلوا بالترتيب المحكوم، RestartCount=0، صفر خطأ جديد في اللوجات،
  health gate الرسمي `passes=16`. تفاصيل كاملة (checksums، rollback
  manifest، smoke tests حقيقية بدون معاملات وهمية) في §10 من
  `docs/agent-workflow/handoffs/2026-08-16_REL-16_payment-channels-beach-cashier_claude_handoff.md`.
- **Migration:** `a7b3f2c8e9d1` — إضافية بحتة فوق `e2f3a4b5c6d7`، head
  واحد. تُنشئ `payment_channels` + 4 أعمدة snapshot على
  `payments`/`beach_transactions`، وتزرع default واحد لكل (فرع، طريقة)
  فقط لو الحساب المطابق (1100/1120/1130) موجود ونشط بالفعل. `downgrade()`
  اتأكد فعليًا على Postgres حقيقي (drop نظيف).
- **قنوات تحصيل حقيقية** (`finance.PaymentChannel`): code فريد لكل فرع،
  اسم عربي/إنجليزي، method (cash|card|wallet)، GL إلزامي (لازم active+
  asset+نفس الفرع)، حساب بنكي اختياري (cash يُرفض لو مربوط ببنك)،
  default واحد فقط لكل (فرع، method) عبر unique index جزئي، تعطيل بدل
  حذف. API كامل + شاشة إدارة في `FinanceView.vue` (ar/en RTL/LTR).
- **الربط**: نقطة موحّدة `dining.payment_policy.resolve_tender_channel`
  يستخدمها الشاطئ والدايننج الاتنين — قناة حقيقية أولًا، fallback لمسار
  الحساب القديم (env-based) فقط لو الفرع بلا أي قنوات معرّفة (توافق آمن
  تام مع الفروع القديمة). اللقطة التاريخية (id/code/name/
  settlement_account_code) محفوظة على `Payment`/`BeachTransaction`، وفي
  `DiningSettlement.tender_breakdown` JSON للدايننج.
- **باج محاسبي حقيقي اتصلح**: إلغاء بيع شاطئ كان بيرجع دايمًا لحساب
  1100 (كاش) حتى لو البيع الأصلي كان بالكارت — كانت فجوة موثّقة صراحةً
  في الكود القديم كـ"خارج النطاق". دلوقتي بيستخدم لقطة حساب الاستلام
  الأصلي المحفوظة وقت البيع.
- **⚠️ باج تقني حقيقي اتكشف واتصلح**: كل قيد محاسبي في الشاطئ كان بينادي
  `post_taxed_sale_journal` بالافتراضي `commit_cost_centers=True`، اللي
  بيعمل commit ضمني وسط أي عملية بيع — يعني كل بيع شاطئ من الأساس كان
  بيقفل الـtransaction بدري من غير قصد. ظهر فعليًا وقت بناء سلة البيع
  الـatomic الجديدة (أول صنف كان بيتثبّت في الداتابيز قبل ما نوصل
  للصنف التاني، فرفض صنف لاحق ما كانش قادر يرجع الصنف الناجح). الحل:
  `commit_cost_centers=False` في كل نداءات الشاطئ الأربعة — نفس النمط
  اللي الدايننج بيستخدمه فعليًا من الأول (Gate 1B).
- **باج race حقيقي اتصلح**: أول صف سعة يومي (`get_or_create_inventory`)
  كان check-then-insert بلا حماية — أول بيعتين في نفس اللحظة بالظبط
  كانوا ممكن يتصادموا بـIntegrityError خام (500). اتصلح بـSAVEPOINT
  (`db.begin_nested()`) حوالين الـINSERT بس.
- **سلة بيع atomic حقيقية**: `POST /beach/sell-cart` جديد — كل الأصناف
  في transaction واحدة (إما كلهم ينجحوا أو ولا واحد)، idempotency على
  مستوى السلة كلها. الفرونت إند بيستخدمه أونلاين بدل الحلقة القديمة
  (طلب منفصل لكل صنف، بيع جزئي كان ممكن يحصل فعليًا). طابور الأوفلاين
  لسه per-item عمدًا (قرار نطاق موثّق).
- **شرط وردية مفتوحة إجباري** لأي دفع مباشر في الشاطئ (409
  `NO_OPEN_SHIFT`، نفس شكل الدايننج بالظبط) — كان غايب تمامًا.
- استلام كاش/فكة بالجنيه في كاشير الشاطئ، حد أقصى كمية (100)، واجهة
  إلغاء حقيقية بسبب إجباري (`require_permission` مدير+ موجود بالفعل).
- **تقرير الوردية (X/Z)**: `ShiftEndReport.channel_breakdown` جديد —
  المبيعات مجمّعة حسب القناة الفعلية وقت البيع.
- **مطابقة البنك**: الـauto-match بيقصر المرشحين على الدفعات اللي قناتها
  مربوطة بنفس الحساب البنكي؛ دفعات legacy (بلا قناة) لسه بتترشح عادي.
- **باج ترجمة اتصلح**: `paymentMethodLabel()` في الدايننج كانت بتقارن
  `method === 'split'` حرفيًا، لكن القيمة الفعلية `"split:cash,card"` —
  النص الخام كان بيظهر للمستخدم زي ما هو.
- **باج حساب آجل اتصلح** (شاطئ ودايننج): تعديل رقم موظف بعد lookup ناجح
  كان بيسيب الحساب القديم محمّل من غير مسح.
- **اختبارات جديدة**: 33 اختبار خالص لقنوات التحصيل عبر 3 ملفات (شاطئ،
  دايننج، finance HTTP) — شامل باج الـcommit الضمني وباج الـrace
  والـvoid وmulti-channel split وbank matching.
- **البوابات**: `agent-check.sh` PASS، `git diff --check` نظيف، backend
  `pytest tests/ -v` → **2850 passed, 68 skipped, صفر failure** (2918
  collected)، `alembic heads` → head واحد `a7b3f2c8e9d1`، frontend
  `type-check:all` نظيف (el-kheima + owner)، `test:frontend` **106/106**،
  `test:e2e:mock` **8/8**، owner `test:e2e` **12/12**، `build:all` نظيف،
  docker compose (dev+prod) نظيف.
- تفاصيل كاملة:
  `docs/agent-workflow/handoffs/2026-08-16_REL-16_payment-channels-beach-cashier_claude_handoff.md`

**السابق:** 2026-08-15 — REL-15B: سعر الشاطئ النهائي بلا VAT،
ومطابقة الورديات، وأرشفة منافذ HIST، منشور ومتحقق فعليًا.

- **Production:** الإصدار الفعال
  `/opt/resort-os-releases/df27697d53a7ec93a10ed2f8898945ecb4a434a6`
  من commit `df27697` على branch
  `codex/rel-15-auth-ops-readiness`؛ Alembic
  `e2f3a4b5c6d7 (head)`؛ PostgreSQL وRedis والخدمات سليمة.
- **الشاطئ والوردية:** سعر تذكرة الشاطئ أصبح السعر النهائي المُحصّل بلا
  ضريبة قيمة مضافة. تمت مصالحة 155 حركة نشطة و153 دفعة و130 قيدًا و60
  وردية ذريًا؛ أزيل `20,284.60 EGP` من VAT التجريبي. لا توجد الآن حركة
  نشطة بضريبة أو دفعة لا تطابق سعرها أو قيد شاطئ غير متزن. العينة الظاهرة
  في البلاغ: الوردية `112` أصبحت متوقع `200`، معدود `200`، فرق `0`.
- **منافذ البيع:** المنافذ التشغيلية النشطة هي `Restaurant / المطعم`
  و`Cafe / الكافيه` فقط. أُرشف `Restaurant HIST` و`Cafe HIST` مع الحفاظ
  على الطلبات التاريخية، وأُلغي الطلب الصفري المعلّق `192` فقط.
- **حالة الوردية:** `GET /finance/shifts/current` يعيد `200 + null` عند
  عدم وجود وردية مفتوحة بدل `404` المزعج في Console؛ الأخطاء الحقيقية
  ما زالت تمر كما هي.
- **تسجيل الدخول:** البريد أصبح case-insensitive، كلمة المرور تُعامل كسر
  كامل بلا حذف مسافات، 2FA/الاسترداد/التسجيل الأول للمالك والمحاسب
  والسوبر أدمن مكتملة، tabs المتزامنة لا تكسر refresh family، وحد شبكة
  الموظفين المشتركة أصبح `60/5m` مع قفل محاولات مستقل لكل حساب.
- **الفرع الوحيد:** الحقيقة التشغيلية المثبتة هي فرع واحد باسم
  `El Kheima Beach Resort`. الحسابات الحية الآن 14: الحسابات الأربعة
  المعتمدة سابقًا + 10 موظفين من الـroster الحقيقي؛ لكل حساب عضوية فعالة.
  أُرشف 8 حسابات تجربة وأُلغيت عضوياتها وجلساتها وحالة 2FA/PIN والصلاحيات
  وفُك ربطها من HR، مع Audit واحد؛ dry-run التالي وجد صفر أهداف.
- **الأدوار:** عزل named-role للمالية وHR وCRM وPMS/POS والتشغيل؛ لا يرث
  `timeshare_admin` صلاحيات كاشير/مالية بسبب رقمه، والمحاسب يهبط على
  `/admin/finance` بلا redirect loop. اختبارات 403 السلبية ضمن البوابة.
- **الملكية الجزئية:** إنشاء أول مدير وموظفي الوحدة يعمل، الزيارات وخدمة
  العملاء وبوابة العميل العامة OTP/JWT منشورة. التحصيل الافتراضي لمدير
  الوحدة فقط؛ استثناء الموظف named permission، وبطاقة/بنك فقط بلا cash.
- **تطبيق المالك:** مسار أول دخول وكلمة المرور المؤقتة و2FA أُصلح كاملًا؛
  الصفحة الرئيسية أصبحت decision-first، مع زمن تحديث القاهرة وتحذير
  البيانات القديمة وفلترة تواريخ صحيحة. استجابة الهاتف والتابلت والكمبيوتر
  محسنة، واختبار حي على `412×915` و`1280×800` ناجح بلا overflow أو خطأ JS.
- **الحسابات الحالية:** 10 موظفين حقيقيين مرتبطون بملفات HR نشطة؛ 9 حسابات
  جديدة، واستعادة حساب HR القديم بنفس ID، وإعادة استخدام سجل المحاسب
  الموجود دون تكراره. لا يوجد email collision. المالكـان والمحاسبان لديهم
  bootstrap لمرة واحدة صالح 24 ساعة؛ بقية الموظفين يغيرون كلمة المرور فقط.
  صفوف الحسابات التجريبية المؤرشفة بقيت بأرقامها الداخلية لحماية المراجع.
- **Full gates:** `agent-check.sh` ناجح وجمع 2874 اختبارًا؛ backend full
  `2806 passed, 68 skipped`؛ Staff `106/106` وmock responsive
  `8/8`؛ Owner responsive E2E `12/12`؛ type-check وبناء production ناجحان؛
  migration نظيفة من قاعدة فارغة إلى head.
- **Live acceptance:** 9 حاويات Resort تعمل، كل `RestartCount=0`؛ backend
  وworker وbeat على image/revision واحدة؛ الموقع وwww وStaff وOwner وhealth
  وبوابة العميل HTTP 200؛ المسار المحمي 401؛ TLS SAN يشمل الأربعة؛
  health gate اليدوي `16/16`؛ السجلات بلا خطأ حقيقي بعد النشر.
- **Rollback:** أرشيف المصدر SHA-256
  `af66a3652e2d800c3d741740d547d579259f69c5fc96d20a8e09b8a8b29fcf6d`؛
  dump متحقق بـ`pg_restore --list`:
  `/opt/resort-os-releases/df27697d53a7ec93a10ed2f8898945ecb4a434a6/backups/resort_os_20260815_001751.dump`
  (`751035` bytes، mode `0600`)؛
  صور الرجوع في
  `/var/backups/resort-os/source-releases/df27697d53a7ec93a10ed2f8898945ecb4a434a6-rollback-images.txt`.
- **قرار التشغيل:** القبول التقني مكتمل. UAT البشري للمالك والموظفين
  ما زال مطلوبًا حسب `docs/UAT_REL15_OWNER_STAFF_AR.md` باستخدام الحسابات
  الشخصية التي جرى تجهيزها.

**السابق:** 2026-08-13 — REL-14 (commit `95c30d9`)
**البيئة:** Production — `elkheima.com` / VPS `191.218.161.133`
**قائد التنفيذ والمراجع النهائي:** Codex

هذا الملف يسجل الحقائق الحالية فقط. التاريخ السابق محفوظ في
`docs/archive/2026-07-execution/`.

## PMS-ROOMS-01 — مخزون الغرف الحقيقي (منشور ✅)

- مصدر البيانات: اعتماد Mohamed المباشر في 2026-08-08؛ لا أسعار.
- حُذفت البيانات الصناعية فقط بعد إثبات أن `bookings` و`booking_rooms`
  و`housekeeping_tasks` كلها صفر. الأداة dry-run افتراضيًا، لها confirmation
  حرفي وPostgreSQL advisory transaction lock وAudit marker وidempotency.
- النوعان `Chalet / شاليه` و`Studio / أستديو` بلا `base_rate` أو
  `max_occupancy` أو `amenities` حتى اعتماد حقائقها. خدمة الحجز ترفض النوع
  غير المسعّر بدل إنشاء حجز بصفر.
- الواجهة تعرض النوع المترجم، الدور الأرضي، والإطلالة في الغرف والاستقبال
  واختيار الغرفة بالحجز.
- implementation/release commit: `eda66178762f44ad4661ab98f9cca442ba491bec`.
- DB backup verified:
  `/var/backups/resort-os/database/resort_os_20260808_193804.dump`
  (`628499` bytes، SHA-256
  `99d18514852543a26bb5b34f4e4289eacc5b140d84e825fe147a04f686ace65c`).
- Rollback images manifest:
  `/var/backups/resort-os/source-releases/eda6617-rollback-images-20260808_193823.txt`.
- Exact-source archive:
  `/var/backups/resort-os/source-releases/eda6617.tar.gz`، SHA-256
  `4746a8319612177320746895b2f1b208fcd2e1da41f9f1192f4dc3bccbfd25dd`.
- بعد النشر: `already_applied=true` في dry-run الثاني، marker واحد،
  `RestartCount=0` للخدمات الأربع، public room types يعيدان `null` للسعر،
  والمسار المحمي يعيد `401` بلا توثيق. حساب الأدمن الذي أنشأه Mohamed بقي
  موجودًا ولم تتعامل معه عملية الغرف.

## Decision 0005 — حساب آجل شخصي (منشور ✅)

- موديول `credit` كامل: Customer/Employee accounts، limit/status،
  immutable ledger، cash/bank collections، partial sale refunds، exact reversal،
  audit، pagination.
- تصحيح محاسبي للبريف: الذمم الشخصية على `1160`؛ `1200`
  يظل مخزونًا.
- Dining وBeach POS يدعمان حساب عميل أو موظف، limit override
  بـmanager PIN، وatomic posting بقيد محاسبي إلزامي.
- Beach void يعكس المديونية بدل صناعة حركة كاش، وDining item refund يخفض
  مديونية الحساب بنسبة الـtender مع cap وفروق تقريب محسومة.
- Staff App: `/admin/credit-accounts` للفتح/الكشف/التحصيل/الحالة/
  الحد/العكس حسب الصلاحيات.
- Owner App: total/count في NowScreen + read-only receivables detail.
- نُشر implementation commit `dd26a1f`، ثم follow-up `1d77e7b` لإزالة تعريف
  HTTP مكرر لـOwner في Nginx. الإصدار الفعال النهائي `1d77e7b`.
- جداول الحسابات والحركات موجودة وفارغة مبدئيًا (`0 / 0`)؛ الفرع الوحيد لديه
  GL `1160`؛ لم تُنشأ حركة مالية تجريبية على الإنتاج.

### سجل نشر CREDIT-0005

- DB backup verified:
  `/var/backups/resort-os/database/resort_os_20260808_180257.dump`
  (`609846` bytes، SHA-256
  `1bd9d33edebb667eb4d42b53fd2f4040aaeaa9c90a9c69efec61ab6bc616d70d`).
- Rollback images manifest:
  `/var/backups/resort-os/source-releases/dd26a1f-rollback-images.txt`.
- Final exact-source archive:
  `/var/backups/resort-os/source-releases/1d77e7b.tar.gz`، SHA-256
  `1ef3bea7541a2354b712faa6b4d0ec044978093746e501e66b7ff78365506827`.
- build: backend/celery worker/celery beat/el-kheima/owner succeeded؛ الاستبدال
  تم backend → worker/beat → Staff/Owner → Nginx، وكل الحاويات الجديدة
  `running/healthy` و`RestartCount=0` (Nginx running وبدون healthcheck).
- `https://elkheima.com` و`www` و`app` و`owner` رجعت HTTP `200`؛ HTTP Owner
  رجع `301`؛ credit وowner protected probes رجعت `401` بلا توثيق كما يجب.
- `nginx -t` و`resort-os-healthcheck.service` ناجحان، وفحص السجلات الصارم
  بعد النشر صفر alerts.

## 1. المصدر والإصدار

| البند | القيمة المثبتة |
|---|---|
| فرع الإصدار المنشور | `codex/rel-15-auth-ops-readiness` |
| Resort OS source release (منشور) | `df27697d53a7ec93a10ed2f8898945ecb4a434a6` — REL-15B Beach final-price no-VAT + shift/HIST reconciliation |
| runtime code/config commit | `df27697d53a7ec93a10ed2f8898945ecb4a434a6` |
| Marketing source release | `088cab4c5dc4de85953895abcf9247f7a3cb2773` — محفوظ ولم يُعد بناؤه في REL-15 |
| `origin/main` وقت الإصدار | `2e74bce` — لم يُحرّك كجزء من النشر |
| active Resort release | `/opt/resort-os-current -> /opt/resort-os-releases/df27697d53a7ec93a10ed2f8898945ecb4a434a6` |
| active Marketing release | `/opt/elkheima-marketing-releases/088cab4c5dc4de85953895abcf9247f7a3cb2773` |
| Marketing current link | `/opt/elkheima-marketing-current -> /opt/elkheima-marketing-releases/088cab4c5dc4de85953895abcf9247f7a3cb2773` |
| Compose project / override | `resort-os-prod` / `docker-compose.prod.domain.yml` |
| Alembic head (DB) | `e2f3a4b5c6d7` (canonical case-insensitive user email — مطبّق ✅) |

## Owner Cockpit Phase 6+7+7a — نشر 8 أغسطس 2026

**ما اتضاف (بدون migration — قراءة فقط):**

**Backend:**
- `owner/schemas.py`: schemas جديدة للـ Phase 6+7+7a (`DaySnapshot`، `NowHistoryResponse`، `SalesPerformanceResponse`، `BeachPerformanceResponse`، `ChannelAnalyticsResponse`، `ExpenseAnalyticsResponse`، `ProcurementAnalyticsResponse`، `ShiftMonitorResponse`، `ExceptionsResponse`)
- `owner/services.py`: `get_sales_performance`، `get_beach_performance`، `get_channel_analytics`، `get_expense_analytics`، `get_procurement_analytics`، `get_shift_monitor`، `get_exceptions`، `get_now_history`
- `owner/api/router.py`: 7 endpoints جديدة (`/owner/sales`، `/owner/beach-performance`، `/owner/channel-analytics`، `/owner/expense-analytics`، `/owner/procurement-analytics`، `/owner/shifts`، `/owner/exceptions`، `/owner/now/history`)

**Frontend:**
- `SalesScreen.vue` — أداء المطعم (ABC + هامش) + الشاطئ (تذاكر بالنوع)
- `ExpensesScreen.vue` — مصروفات كـ % من الإيراد + variance flags + مشتريات الموردين
- `ShiftsScreen.vue` — تنبيهات (critical/attention/watch) + مراقبة الورديات
- `NowScreen.vue` — sparklines حقيقية من `/owner/now/history?days=7`
- `AppShell.vue` — bottom nav من 2 لـ 5 tabs
- `router/index.ts` — 3 routes جديدة (sales/expenses/shifts)
- `public/icon-192.png` + `public/icon-512.png` — PWA icons من الـ logo الأصلي

**التحقق:**
- ✅ 150 owner tests passed
- ✅ TypeScript نظيف
- ✅ Build: 16 entries precached
- ✅ backend: running restarts=0
- ✅ owner: running restarts=0
- ✅ `https://owner.elkheima.com/icon-192.png` → HTTP 200
- ✅ `https://owner.elkheima.com/icon-512.png` → HTTP 200
- ✅ `GET /api/v1/owner/now/history` endpoint موجود في الـ router

## Owner Cockpit — حالة المراحل

| # | المرحلة | الحالة |
|---|---|---|
| 1 | Metric contracts | ✅ مكتمل |
| 2 | Isolation + safety rails | ✅ مكتمل |
| 3 | Aggregation APIs (now/performance) | ✅ مكتمل |
| 4 | Owner PWA (Now + Performance) | ✅ مكتمل |
| 5 | مراجعة الأرقام مع محمد | ✅ مكتمل (2026-08-08) |
| 6 | Sales/Beach/Channel/Expense/Procurement analytics | ✅ مكتمل (2026-08-08) |
| 7 | Shift monitoring + Exceptions engine | ✅ مكتمل (2026-08-08) |
| 7a | PWA polish — icons + sparklines | ✅ مكتمل (2026-08-08) |
| 8 | Security review + production gate | ✅ مكتمل في REL-15 (2026-08-14) |
| ~~9~~ | ~~Unit economics~~ | محذوف بقرار محمد |
| ~~10~~ | ~~Scenario sandbox~~ | محذوف بقرار محمد |

## REL-12 — نشر 9 أغسطس 2026 (commit `403bbd7`)

**إغلاق فجوة PMS checkout/folio الموثّقة في REL-11 §8.1 — بتأكيد صريح من محمد**

محمد أكّد: "الاستقبال بيحصّل كل حاجة مرة واحدة وقت الخروج" — يعني قرار
سياسة التسوية واضح، مفيش لبس. `_post_checkout_journal` كانت بتقفل
`booking.total_rate` (سعر الغرفة) بس مقابل حساب 1150، وأي "شحن على حساب
الغرفة" من الشاطئ/الدايننج (`FolioCharge.charge_type` = beach/dining)
كان بيفضل قايم على 1150 للأبد بعد الـcheckout بصمت.

**الإصلاح**: بيجمع أي شحنة beach/dining لسه مش `is_settled` على فوليو
الحجز (بما فيها VAT/service_charge) ويضيفها لمبلغ التسوية، يعلّم الشحنات
دي settled، ويقفل الفوليو (`status=closed`). الـقفل بيتم عبر
`finance.crud.lock_folio_for_update` (نفس القفل البلوكينج اللي
`add_folio_charge` بتاخده) — يمنع سباق حقيقي لو شحنة جديدة بتتضاف بالظبط
وقت الـcheckout. **قرار موثّق**: مفيش استدعاء لـ`finance.services.
settle_folio` عمدًا — الدالة دي عندها `can_checkout` gate بيرفض أي فوليو
عليه شحنة أصلاً قبل ما تتسوّى، يعني مش موصولة بأي مسار حقيقي فعليًا
(فجوة منفصلة، برّه نطاق الإصلاح ده).

تست جديد (`test_checkout_settles_room_charged_beach_and_dining_extras`)
بيثبت: فوليو فيه شحنة شاطئ (300+42 ضريبة) وشحنة دايننج (150)، بعد
checkout — القيد المحاسبي الواحد بيقفل `room_total + 300 + 42 + 150`
بالظبط، الشحنتين بقوا `is_settled=True`، والفوليو `status=closed`.

لا migration — Alembic head `d0e1f2a3b4c5` بدون تغيير.

**دورة النشر (REL-12، 2026-08-09 ~15:47 Cairo):**
- ✅ نسخة احتياطية: `resort_os_20260809_124603.dump` (620K، 1472 TOC entries — مثبّت)
- ✅ SHA-256 أرشيف مطابق على الطرفين: `41835375faf327b836822f5aadfc90fd40e4a8114588f98dc799f342d6e5f78e`
- ✅ rollback tags: 6 خدمات مؤرشفة كـ `resort-os-rollback/<svc>:pre-403bbd7`
- ✅ rollback manifest: `/var/backups/resort-os/source-releases/403bbd7-rollback-images.txt`
- ✅ validate_prod_env: passed
- ✅ بناء الصور: backend/celery_worker/celery_beat/el_kheima — Built بنجاح
- ✅ preflight import: `El Kheima Beach`
- ✅ alembic heads/upgrade: `d0e1f2a3b4c5` (head) — لا migration
- ✅ استبدال تدريجي: backend → celery_worker/beat → el_kheima → nginx (كل مرحلة healthy + RestartCount=0)
- ✅ health check: `{"status":"ok","database":{"status":"ok","latency_ms":8.7},"redis":{"status":"ok","latency_ms":1.4}}`
- ✅ elkheima.com/www/app: كلهم HTTP 200
- ✅ symlink: `/opt/resort-os-current -> /opt/resort-os-releases/403bbd7`
- ✅ DB sanity: `users=5, branches=1`
- ✅ RestartCount=0 لكل الحاويات — لوجات نظيفة صفر traceback/critical/fatal
- ✅ مفيش قاعدة بيانات استرجاع مؤقتة اتسابت

## REL-11 — نشر 9 أغسطس 2026 (commit `92aa769`)

**فحص شامل نهائي قبل الإطلاق: إغلاق فجوة أمان /ops + N+1 + قيود يومية حقيقية + دفتر يومية إداري**

**ما اتنشر:**
- **أمان**: `/ops` (استقبال/غرف/حجوزات/تدبير منزلي) كان من غير `requiredRole` خالص
  على مستوى الأب — الحماية الوحيدة كانت `requiredPermission` لكل شاشة فرعية.
  اتضاف `requiredRole: 'receptionist'` كطبقة دفاع تانية مستقلة.
- **N+1**: `inventory.list_purchase_orders/list_purchase_requests/list_stock_counts`،
  `maintenance.list_work_orders`، و`finance.list_journal_entries` (`selectinload` بدل
  lazy queries متكررة). `pms.create_booking` كان بيعيد نداء `get_available_rooms`
  و`get_room_type` لكل غرفة في الحجز بدل مرة واحدة، وبيعيد `get_room` تاني رغم إن
  الصف نفسه متقفول ومتاح بالفعل من `locked_rooms`.
- **قفل PMS**: `lock_room_for_booking` كان ناقص `.populate_existing()` (نفس فئة
  الباج الموثّقة في CLAUDE.md §13⓫).
- **صمت محاسبي**: `post_simple_revenue_journal` كان بيبتلع فشل (حساب غير معرّف/فشل
  تحويل عملة/استثناء غير متوقع) ويرجع `None` من غير أي `log` — بقى فيه `logger.error`/
  `logger.exception` على المسارات التلاتة.
- **دفتر اليومية**: تاب إداري جديد في `FinanceView.vue` (`GET /finance/journal-entries`،
  مدير+) — فلترة بالتاريخ/المصدر، صفوف قابلة للطي بتعرض كل سطر مدين/دائن. باج حقيقي
  اتصلح أثناء المراجعة: `JournalLineRead` مكانش فيه `account_code`/`account_name` خالص
  (بس `account_id`) رغم إن الشاشة بترسمهم مباشرة — عمود "الحساب" كان هيفضل فاضي دايمًا.
  اتضاف `@model_validator(mode="before")` (نفس نمط `dining.DiningItemRead`) + eager
  loading لـ`.lines.account` في `list_journal_entries`. مفتاحين i18n مكررين بالغلط
  (`tabs`, `refresh` داخل نفس كائن finance) اتشالوا، ومفتاح `loadJournalError` غلط
  (الفعلي `journal.loadError`) اتصلح — اكتشفهم i18n validator نفسه (`validate-i18n.mjs`)
  فعليًا وقت `test:frontend`.
- **موثّق مش مُصلَح**: فجوة محاسبية حقيقية في `PMS checkout` — التسوية بتقفل رصيد سعر
  الغرفة بس مقابل حساب 1150، مش أي شحنات "على حساب الغرفة" (شاطئ/دايننج) — تفاصيل
  كاملة في §8.1 تحت، قرار سياسة تسوية لازم يرجع لمحمد.
- لا migration — Alembic head `d0e1f2a3b4c5` بدون تغيير
- تست جديد: `test_list_journal_entries_lines_include_account_code_and_name`
- الباك إند الكامل عدّى 100% (صفر فشل)، `el-kheima` type-check/test:frontend
  (95 اختبار)/build نظاف الكل، `agent-check.sh` أخضر

**دورة النشر (REL-11، 2026-08-09 ~14:50 Cairo):**
- ✅ نسخة احتياطية: `resort_os_20260809_115233.dump` (620K، 1472 TOC entries — مثبّت
  فعليًا عبر `pg_restore --list` جوه الحاوية)
- ✅ SHA-256 أرشيف مطابق على الطرفين: `90e5445d28fb6fb97d1993d98d896ec48e2195e0a98a0dc32a1af23b7e03d47c`
- ✅ rollback tags: 6 خدمات مؤرشفة كـ `resort-os-rollback/<svc>:pre-92aa769`
- ✅ rollback manifest: `/var/backups/resort-os/source-releases/92aa769-rollback-images.txt`
- ✅ validate_prod_env: passed
- ✅ بناء الصور: backend/celery_worker/celery_beat/el_kheima — Built بنجاح
  (marketing_site/owner متلمسوش — برّه نطاق هذه الدفعة)
- ✅ preflight import: `El Kheima Beach`
- ✅ alembic heads/upgrade: `d0e1f2a3b4c5` (head) — لا migration
- ✅ استبدال تدريجي: backend → celery_worker/beat → el_kheima → nginx (كل مرحلة
  اتأكد منها healthy + RestartCount=0 قبل الانتقال للتالية)
- ✅ health check: `{"status":"ok","database":{"status":"ok","latency_ms":1.7},"redis":{"status":"ok","latency_ms":1.3}}`
- ✅ elkheima.com: HTTP 200 / www.elkheima.com: HTTP 200 / app.elkheima.com: HTTP 200
- ✅ symlink: `/opt/resort-os-current -> /opt/resort-os-releases/92aa769`
- ✅ TLS SAN: `app.elkheima.com, elkheima.com, owner.elkheima.com, www.elkheima.com`
- ✅ DB/Redis: loopback-only (`127.0.0.1:5436`/`127.0.0.1:6381`) — بدون تغيير
- ✅ DB sanity: `users=5, branches=1` — نفس البيانات الحقيقية، صفر تلاعب
- ✅ `GET /api/v1/finance/journal-entries` بدون توكن → `401` (المسار الجديد حي ومحمي)
- ✅ RestartCount=0 لكل الحاويات المستبدلة — لوجات نظيفة صفر traceback/critical/fatal
- ✅ مفيش قاعدة بيانات استرجاع مؤقتة اتسابت
- ملاحظة: جلسة مستخدم حقيقية شغالة (WebSocket alerts/shifts) وقت النشر — استمرت من
  غير انقطاع ملحوظ في اللوج أثناء استبدال backend

## REL-10 — نشر 7 أغسطس 2026 (commit `427ae82`)

**POS-BEACH-01: فيتشر خريطة الشمسيات + الفنادق في كاشير الدايننج + 5 إصلاحات**

**ما اتنشر:**
- `dining/models.py`: `b2b_contract_id` + `beach_location_id` على `DiningOrder`
- `dining/api/router.py`: `_enrich_order/_enrich_order_list` — `hotel_name` + `beach_location_label` بـ 2 queries، GET `/dining/b2b-contracts`، GET `/dining/reports/hotel-consumption`
- Migration `a3f9c1d2e4b5`: ADD COLUMN b2b_contract_id + beach_location_id + partial unique index
- Frontend: إصلاح `hotel_name` mismatch، cash presets (50-500ج)، i18n beachMap، ShiftDashboard hotel label
- `POSBeachMapWorkspace.vue` + `POSHotelSelector.vue`: components جديدة
- 9 tests جديدة — 2342 backend passed، 95 frontend passed، TypeScript نظيف

**دورة النشر (REL-10، 2026-08-07 ~07:25 Cairo):**
- ✅ نسخة احتياطية: `resort_os_20260807_042156.dump` (588K، 1419 entries — مثبّت)
- ✅ SHA-256 أرشيف مطابق على الطرفين: `4eb5f7f42e38af89e31e1b233ff48821de2cf393a38872cebbe2532e41485bbd`
- ✅ rollback tags: 5 خدمات مؤرشفة كـ `resort-os-rollback/<svc>:pre-427ae82`
- ✅ rollback manifest: `/var/backups/resort-os/source-releases/427ae82-rollback-images.txt`
- ✅ validate_prod_env: passed
- ✅ بناء الصور: backend/celery_worker/celery_beat/el_kheima — Built بنجاح
- ✅ preflight import: `El Kheima Beach`
- ✅ migration `a3f9c1d2e4b5`: applied (`52f4544e50d2 -> a3f9c1d2e4b5`)
- ✅ استبدال تدريجي: backend → celery_worker/beat → el_kheima → nginx
- ✅ health check: `{"status":"ok","database":{"status":"ok"},"redis":{"status":"ok"}}`
- ✅ elkheima.com: HTTP 200 / www.elkheima.com: HTTP 200 / app.elkheima.com: HTTP 200
- ✅ symlink: `/opt/resort-os-current -> /opt/resort-os-releases/427ae82`
- ✅ Alembic current: `a3f9c1d2e4b5 (head)`
- ✅ DB: columns `b2b_contract_id` + `beach_location_id` موجودتين في `dining_orders`
- ✅ RestartCount=0 لكل الحاويات — لوجات نظيفة صفر ERROR/CRITICAL



**dining N+1 batch-load + 41 test جديدة + مراجعة دين تقني**

**ما اتنشر:**
- `dining/services.py`: batch-load في `create_order`, `add_items_to_order`, `sync_offline_order`, `_deduct_inventory_for_order` — صفر N+1 queries داخل الـ loops
- `dining/crud.py`: `get_items_by_ids()`, `get_variants_by_ids()` جديدتين
- `inventory/crud.py`: `get_products_by_ids_any_branch()`, `get_warehouses_by_ids()` جديدتين
- `test_dining_router_coverage.py`: 41 test جديدة (menu CRUD، tables، orders HTTP، kitchen/KDS، public endpoints)
- `docs/audits/TECHNICAL_DEBT_AND_COVERAGE_AUDIT.md`: مراجعة دين تقني شاملة مرتبة بالأولوية
- لا migration جديدة — Alembic head `52f4544e50d2` بدون تغيير
- 2333 pytest passed، type-check نظيف، build نظيف

**دورة النشر (REL-09، 2026-08-06 ~05:25 Cairo):**
- ✅ نسخة احتياطية: `resort_os_20260806_021750.dump` (588K — مثبّت)
- ✅ SHA-256 أرشيف مطابق على الطرفين: `a04aaf6b3d1cffacda5d55645fc4958b1e19f9da5209a1e57a6681f21ca1793c`
- ✅ rollback tags: 5 خدمات مؤرشفة كـ `resort-os-rollback/<svc>:pre-fd105f6`
- ✅ rollback manifest: `/var/backups/resort-os/source-releases/fd105f6-rollback-images.txt`
- ✅ validate_prod_env: passed
- ✅ بناء الصور: backend/celery_worker/celery_beat/el_kheima — Built بنجاح
- ✅ preflight import: `✓ El Kheima Beach`
- ✅ alembic heads: `52f4544e50d2` (head) — لا migration
- ✅ استبدال تدريجي: backend → celery_worker/beat → el_kheima → nginx
- ✅ health check: `{"status":"ok"}` — 8/8 حاويات running/healthy، restarts=0
- ✅ app.elkheima.com: HTTP 200 / elkheima.com: HTTP 200 / www.elkheima.com: HTTP 200
- ✅ symlink: `/opt/resort-os-current -> /opt/resort-os-releases/fd105f6`
- ✅ logs نظيفة — صفر ERROR/CRITICAL

## REL-08 — نشر 5 أغسطس 2026 (commit `7d00917`)

**POS-03 + POS-03b: دعم الدفع بعملات متعددة (مطعم/كافيه + شاطئ)**

**ما اتنشر:**
- `Payment.fx_rate` عمود جديد (migration `52f4544e50d2`) — سعر الصرف وقت الدفع
- المطعم/الكافيه: `OrderStatusUpdate`/`SplitBillPayment` بيقبلوا `payment_currency`/`payment_fx_rate`
- الشاطئ: `BeachSellRequest` يقبل `payment_currency`/`payment_fx_rate` — الفكة دايمًا بالجنيه
- `build_shift_end_report`: `ForeignCurrencySummary` لكل عملة أجنبية (expected/variance)
- `POSPaymentModal.vue` + `BeachPOSView.vue`: اختيار عملة، عرض المطلوب بالأجنبية، الفكة
- `FinanceView.vue`: tab أسعار الصرف (المدير يضيف/يشوف من الواجهة)
- 2292 pytest passed، 95 frontend tests، type-check نظيف، build نظيف

**دورة النشر (REL-08، 2026-08-05 ~17:39 Cairo):**
- ✅ نسخة احتياطية: `resort_os_20260805_172441.dump` (584K، 1419 TOC entries — مثبّت)
- ✅ SHA-256 أرشيف مطابق على الطرفين
- ✅ validate_prod_env: passed
- ✅ rollback tags: 6 خدمات مؤرشفة كـ `resort-os-rollback/<svc>:pre-7d00917...`
- ✅ بناء الصور: backend/celery_worker/celery_beat/el_kheima — Built بنجاح
- ✅ migration `52f4544e50d2`: applied (7b4d81dc08ee → 52f4544e50d2)
- ✅ استبدال تدريجي: backend → celery_worker/beat → el_kheima → nginx
- ✅ health check: `{"status":"ok","database":{"status":"ok"},"redis":{"status":"ok"}}`
- ✅ app.elkheima.com: HTTP 200 / elkheima.com: HTTP 200
- ✅ symlink: `/opt/resort-os-current -> /opt/resort-os-releases/7d00917...`
- ✅ 8/8 حاويات running/healthy

## POS-03b — دعم الدفع بعملات متعددة للشاطئ (commit `f68b232`، 2026-08-05)

قرار Mohamed: الشاطئ يدعم نفس الميزة + الفكة دايمًا بالجنيه.
**منشور على VPS في REL-08 ✅**

**ما اتعمل:**
- `BeachSellRequest` يقبل `payment_currency`/`payment_fx_rate` اختياري مع validator (لو currency≠EGP بدون fx_rate → 422)
- `_sell_ticket_no_commit`: يحفظ currency/fx_rate كـ transient attrs على tx
- `_record_shift_payment`: يمرّر currency/fx_rate لـ `create_direct_payment` — Payment.amount دايمًا EGP-equivalent
- الفكة دايمًا بالجنيه (قرار Mohamed 2026-08-05) — الشاشة تعرض "الفكة = X جنيه"
- `BeachPOSView.vue`: أزرار اختيار عملة (EGP/USD/EUR)، عرض المطلوب بالأجنبية، حقل استلام، الفكة بالجنيه، `fetchFxRates` عند mount
- ترجمات ar/en: 7 مفاتيح `beachPos` جديدة
- 5 تستات جديدة (beach) + 3 schema validation: 2292 passed، صفر failure
- type-check نظيف، build نظيف، agent-check passed، Alembic single head (بدون migration إضافية)

**Gate (POS-03 + POS-03b مع بعض):** 2292 pytest passed، 95 frontend، type-check نظيف، build نظيف.

## POS-03 — دعم الدفع بعملات متعددة للمطعم/الكافيه (commit `e2c31af`، 2026-08-05)

بطلب صريح من Mohamed (بريف `docs/agent-workflow/POS-03_MULTI_CURRENCY_CASHIER_PLAN_AR.md`)
— **غير منشور على VPS بعد، ينتظر قرار Go من Mohamed بعد مراجعة §3.3**.

**ما اتعمل:**
- `Payment.fx_rate` عمود جديد (migration `52f4544e50d2`) — سعر الصرف وقت الدفع
- `create_direct_payment` بيقبل `currency`/`fx_rate` — دفعة كاش بعملة أجنبية تُسجَّل بالمعادل EGP في `amount` والعملة الأصلية في `currency`/`fx_rate`
- `OrderStatusUpdate`/`SplitBillPayment` بيقبلوا `payment_currency`/`payment_fx_rate` (اختياري — لا يكسر أي بيع EGP حالي)
- `build_shift_end_report`: `ForeignCurrencySummary` بيضيف `expected_amount`/`variance` لكل عملة أجنبية — الكاشير يشوف "معدود 70 USD — متوقع 70 USD — فرق 0" بدل رقم جنيه واحد مبلوع
- `POSPaymentModal.vue`: اختيار عملة (EGP/USD/EUR)، عرض المطلوب بالعملة الأجنبية، حقل الاستلام، الفكة، سعر الصرف الحالي مباشر
- `FinanceView.vue`: tab جديد "أسعار الصرف" — المدير يضيف ويشوف الأسعار من الواجهة (بديل Postman)
- 10 تستات جديدة (`test_pos03_multi_currency.py`) — كلها أخضر

**ما ينتظر قرار Mohamed (§3.3 في البريف):**
- الشاطئ محتاج نفس الميزة ولا المطعم/الكافيه بس الأول؟
- الباقي (فكة) بيترجع جنيه دايمًا ولا بنفس العملة؟
- شاشة أسعار الصرف يدوية كافية ولا ربط تلقائي بمصدر خارجي؟
- العملات المدعومة USD/EUR بس ولا نضيف غيرهم؟

**Gate**: 2284 pytest passed، 95 frontend، type-check نظيف، build نظيف، migration تطبّق على prod بـ `alembic upgrade head`

أرشيف Resort OS:
`/var/backups/resort-os/source-releases/5df8191.tar.gz`،
SHA-256 `df209816d2ac9547d42cfc64c45c007a939d7d90f2a586832d30d1fde7e02963`.
(أرشيف `821a718` وما قبله محفوظ كما هو.)

أرشيف سابق (`821a718`):
`/var/backups/resort-os/source-releases/821a718.tar.gz`،
SHA-256
`542cdaa35f7dfb6ae1dd6da68c825d65954da2606a57783ff177c479f35a4411`.
(أرشيفات `5b02010`، `a3e8abb`، `ddfbaaa`، `4a0a777`، `8597535`، `b1db886`، `0d55717`، `4ca10c1` السابقة ما زالت محفوظة كما هي.)

أرشيف Marketing:
`/var/backups/resort-os/marketing-source-releases/79130a6.tar.gz`،
SHA-256 `f8e454beb95a48ac8c72ec8705c36ca50948289f2e690587a9bb629ee4fe5a9f`.
(أرشيفات `1371975`، `16f8f2c`، `0b0321f`، `4fba5b6`، `53bf7a3` السابقة ما زالت محفوظة كما هي.)

مجلدا المصدر القديمان `/opt/resort-os` و
`/opt/elkheima-marketing-website` محفوظان كما كانا، وغير مستخدمين كمصدر
للإصدار الفعال ولم يُنظفا أو يُعاد ضبطهما.

## 2. الخدمات الفعالة

- **2026-08-04 — REL-07: `5df8191` (8 commit فوق `821a718`) + Marketing
  `79130a6` (بتفويض مباشر من Mohamed: "انت القائد للنهاية... اعمل ما
  يلزم")**: `backend`, `celery_worker`, `celery_beat`, `el_kheima` اتبنوا
  ونُشروا من `5df8191`؛ `marketing_site` اتبنى من `79130a6` (المستودع
  المستقل) بنفس الدورة.
  - **فواتير/إيصالات PDF عربية**: 3 باجات متسلسلة اتصلحوا في
    `app/core/kernel/reports.py` — مفيش خط عربي متسجّل خالص (النص العربي
    كان بيترسم بـHelvetica، صفر glyphs عربي)، الخط العربي المتاح مالوش
    حروف لاتينية خالص (تسجيله لوحده كان هيمسح أي كلمة إنجليزية)،
    والتذييل كان بيترسم من غير إعادة تشكيل (`_add_footer` مكنش بينادي
    `_t()`). الحل: `_split_script_runs`/`_draw_mixed` يرسموا كل جزء
    بالخط اللي بيغطّيه فعليًا، + لوجو المنتجع الحقيقي على الإيصال
    الحراري (مكنش موجود خالص)، + تصميم أرقى (فواصل متقطّعة، تفصيل سعر،
    قسم إجمالي واضح). الفونتات/اللوجو اتحطّوا في `app/assets/` عشان
    يتنسخوا فعليًا لصورة الإنتاج (`python:3.11-slim` مفيهوش فونتات نظام).
  - **مدونة حقيقية**: كانت skeleton كامل — endpoint قائمة بس (بدون
    `body`/`cover_image`)، مفيش endpoint لمقال منفرد خالص، صفر مقالات
    مزروعة. اتضاف `GET /hub/blog/posts/{slug}` (404 للمسودات/الناقص،
    بيزوّد `views_count` فعليًا)، `cover_image` بقى متعرّض في القائمة،
    و6 مقالات حقيقية (نص عربي منقول زي ما هو من مشروع
    `elkheima-beach-resort` القديم بطلب صريح من Mohamed) اتزرعوا عبر
    `app.seed._seed_blog_posts` (idempotent upsert بالـslug، نفس نمط
    `_seed_chart_of_accounts` — محتوى حقيقي آمن للتشغيل المباشر على
    الإنتاج، مش بيانات تجريبية).
  - **إصلاح شامل للموقع التسويقي** (`elkheima-marketing-website`، commit
    `79130a6`): حذف `useModulesStore`/`fetchModules` بالكامل (كان بينادي
    `/modules/public` غير موجود خالص في resort-os — نظام تفعيل/تعطيل
    الموديولات اتشال عمدًا من الباك إند، ومفيش أي مستهلك حقيقي لنتيجة
    النداء أصلاً)، وقف نداء `/settings/public` المماثل في
    `useMediaSettings` (نفس القصة — endpoint مش موجود، fallback بصمت).
    إصلاح باج تصميم حقيقي في `Timeshare.vue`/`Booking.vue`: `<SEOHead>`
    كان sibling قبل الـ`<div>` الجذر بدل ما يكون جواه — بيخلّي الكومبوننت
    عنده root عنصرين، وده بالظبط سبب تحذير Vue "renders non-element root
    node that cannot be animated" وخطأ `InvalidStateError` وقت الانتقال
    بين الصفحات اللي Mohamed بعت سكرين شوت بيه. زرار "🏖️ اطلب من مكانك"
    في صفحة الشاطئ العامة كان بيسمح لأي زائر موقع عشوائي يبعت "طلب" وهمي
    (فعليًا رسالة تواصل يدوية بس، بدون أي تحقق حضور فعلي في المنتجع) —
    بقى كارت وصف للخدمة بس، مش نموذج طلب حي.
  - **اكتشاف جانبي أثناء المراجعة**: لقيت 147 ملف تعديل غير محفوظ (commit)
    على `/opt/resort-os` (السيرفر) — راجعتها كلها، اتضح إن 100 منها مجرد
    الفرق الطبيعي بين `main` والفرع التشغيلي (مفيش خطر)، والـ18 الباقية
    (إصلاحات عزل فروع/تعارض دفعات/تشفير PII كانت موثّقة في بريف من وكيل
    اسمه Kiro بتاريخ 29 يوليو) طلعت متعملة لها commit ونشر بالفعل قبل كده
    (إصدار `258c99c`، موجود جوه `821a718`) — يعني مفيش حاجة ضاعت، الفولدر
    ده مجرد نسخة قديمة مش مستخدمة في النشر أصلاً (موثّق في `DEPLOYMENT.md`
    كـ"legacy source snapshot; not a deploy target").
  - **بوابة الجودة**: `agent-check.sh`، pytest كامل (backend)، alembic
    heads (head واحد `7b4d81dc08ee`، صفر migration جديدة هذه الدفعة)،
    `pnpm type-check:all`، `pnpm --filter el-kheima test:frontend`
    (95/95)، `pnpm build:all`، بناء الموقع التسويقي + type-check +
    `validate:truth` — كله أخضر.
  - **النشر**: نسخة احتياطية DB اتاتأكدت (`pg_restore --list`، 1408 TOC
    entry)، rollback tags للـ6 خدمات، استبدال تدريجي (backend → celery →
    el_kheima → nginx، وmarketing_site منفصل)، health check رسمي 14/14،
    تحقق حي فعلي عبر متصفح Playwright على الدومين الحقيقي (صفر console
    errors، صفر 404s، المدونة والفاتورة اشتغلوا صح).

- **2026-08-03 — دفعة `821a718` (23 commit فوق `5b02010`، بتفويض مباشر من
  Mohamed خارج دورة Codex المعتادة)**: `backend`, `celery_worker`,
  `celery_beat`, `el_kheima` اتبنوا ونُشروا كلهم من `821a718`.
  `marketing_site` اتبنى من نفس السياق الحالي (`1371975`، بدون تغيير في
  مصدره) كجزء من أمر البناء الموحّد فقط.
  - **HR/الأدمن**: بحث/فلترة حقيقية للموظفين والمستخدمين، تعديل/تغيير حالة
    الموظف، تحميل الرواتب Excel/PDF وقسائم راتب فردية، ملف موظف موحّد،
    إصلاح IDOR حقيقي في `GET /hr/employees/{id}` (كاشير فرع كان يقدر يقرا
    بيانات موظف فرع تاني)، فك قفل حساب/إعادة ضبط 2FA إداري (step-up)،
    إدارة جلسات مستخدم تاني (عرض/إنهاء، step-up)، فلترة سجل التدقيق بتاريخ
    + اسم فاعل، حذف نظام إشعارات كان مبني بالكامل بدون أي مستهلك خالص.
  - **مالي حقيقي**: `vat_percentage`/`service_charge_percentage` كانا
    بيتقروا من env var بس مهما اتغيّروا في الإعدادات — بقوا فعليًا
    DB-driven في dining/beach/finance الثلاثة.
  - **ملكية جزئية**: إدارة وحدات فعلية (CRUD)، قائمة انتظار حقيقية، تذكيرات
    واتساب (صيانة مستحقة/انتهاء عقد)، نسبة إشغال في اللوحة، بوابة صاحب
    عقد ذاتية كاملة (OTP، تحميل PDF العقد)، تنبيهات واتساب في الاتجاهين
    لطلبات الزيارة وتذاكر الدعم (مكانتش موجودة خالص)، زرار توليد مستحقات
    صيانة يدوي. **باج أمني حقيقي اتصلح قبل النشر مباشرة**: إنتاج فحص fail
    -closed جديد لـ`TIMESHARE_PORTAL_TOKEN_SECRET`/`SURVEY_TOKEN_SECRET`
    (بديل مفتاح فاضي/افتراضي كان ممكن يسمح بتزوير توكن بوابة عميل تايم
    شير بمعرفة الكود العام على GitHub بس). `.env.prod` في هذا الإصدار
    اتضاف له `TIMESHARE_PORTAL_TOKEN_SECRET` حقيقي (32+ حرف عشوائي) أول
    مرة — مكانش موجود قبل كده، الميزة اتبنت بعد آخر نشر.
  - **دايننج**: هوية ضيف + طلب ذاتي عابر للمنافذ + ملاحظات لكل صنف، منيو
    ضيف بـ4 لغات (ar/en/ru/it)، idempotency لطلب الضيف + بث خريطة الطاولات
    الحي، تسالي الكافيه.
  - 4 migrations جديدة (`a7c3f0e9d5b2`، `f1e6c8b4a3d7`، `7e5e126360d5`،
    `7b4d81dc08ee`) — Alembic head واحد `7b4d81dc08ee`، اتأكد `alembic
    upgrade head` شغال نظيف على الإنتاج الحقيقي قبل الاستبدال.
- `marketing_site` بُني ونُشر من `53bf7a3` — جولة مراجعة كاملة لباقي شاشات
  الموقع التسويقي (Rooms/Beach/Restaurant/Activities/Events/Packages/
  Products/FAQ/Home/Contact/Timeshare/booking modal) بعد إغلاق MKT-04،
  لقيت 3 دفعات باجات حقيقية: (١) 7 استمارات تواصل عامة (booking/contact/
  timeshare/spa/room-service/sunbed + usePageBooking المشتركة) كانت بتعيد
  استخدام نفس idempotency key حتى بعد فشل الإرسال — لو رد نجاح ضاع فعليًا
  بعد ما الباك إند كتب الصف (network drop/timeout)، وبعدين الزائر عدّل
  حاجة بسيطة وأعاد الإرسال، كان بيتعلّق للأبد على 409 idempotency_conflict
  من الباك إند من غير أي مخرج غير ريفريش الصفحة — اتصلح بتوليد مفتاح جديد
  عند أي فشل. (٢) تسريب حقيقي من بوابات PUBLIC_TRUTH: "4.2★" (تقييم مفبرك)
  و"12,500 m²" في Beach.vue، 4 إجابات FAQ برقم خصم/عربون صريح، كارت "وفّر
  حتى 30%" في Packages.vue، وبادج سعة "200+ ضيف" في Events.vue — كلهم
  كانوا ظاهرين لأي زائر حقيقي لأنهم راكبين على بوابة عامة (amenities/
  packages) مفعّلة بدل بوابتهم الخاصة (prices/promotions/ratings/
  numericStats، لسه fail-closed). زائد فخين خاملين (تقييم + تصنيف "3 نجوم"
  في Home.vue، وتضارب سعر رومانسي 300ج/$15 حسب اللغة في Rooms.vue) اتأمّنوا
  احتياطيًا قبل ما يتفعّلوا بالغلط لاحقًا. (٣) كاردز Products.vue كانت
  بتستخدم مسارات خام بدل localePath()، عكس باقي الموقع بالكامل. تفاصيل
  كاملة في handoff MKT-05.
- `marketing_site` بُني ونُشر بعد كده من `1371975` (MKT-06) — Mohamed
  رفع screenshot لسكرول أفقي فاضي طويل في `/ar/contact` بس (باقي اللغات
  سليمة). السبب: حقل honeypot مضاد للبوتات كان مخفي بإزاحة فيزيائية ضخمة
  (`-left-[10000px]`) من غير أي عنصر أب positioned يحتوي الـoverflow —
  في LTR المتصفح بيتجاهل السكرول للإحداثيات السالبة بصمت، لكن في RTL
  نقطة بداية السكرول بتتقلب وبتسمح فعليًا بالوصول للمنطقة السالبة دي،
  فعرض الصفحة الفعلي كان بيتوسّع 10000px. اتصلح بـ`sr-only` (تقنية
  Tailwind قياسية، clip-based، صفر إزاحة فيزيائية) — نفس التقنية
  المستخدمة فعلاً في مكان تاني بالموقع. اتفحص باقي الموقع لنفس النمط
  (`-left-[Npx]`/`-right-[Npx]`) — التطابق الوحيد التاني (blob زخرفي في
  CTASection.vue) محاط فعليًا بـ`overflow: hidden` صح، مش نفس الباج.
  اتأكد الإصلاح حيًا: الكود القديم (`10000px`) اختفى تمامًا من الـbundle
  المنشور، و`sr-only` موجود فعليًا.
- Backend image:
  `sha256:abbd5f245b5e3d84efc2e5c9215f06c08576a465f316e89e26fcf0842655b28a`.
- Celery worker:
  `sha256:c58a764a0c87475db671e8e7d1e9302e8ef1979b9da65f1bf4025a2cee6a2fd6`.
- Celery beat:
  `sha256:9e304ad5e074762707aaab2097a273f31f0aeaba5713ddda7bd95e393da3c1d0`.
- El Kheima staff app (من `b1db886`، غير متغيّر هذه الجولة):
  `sha256:f135b11a4d2d7799afd011934a093eb14ed14921b86bbd807d31582a1082c673`.
- Marketing image:
  `sha256:fafe1eb8576b3c2b0c2cd2da3346cbe2bf2eb7d98f26a4619df1d81d707a9ad9`.
- Nginx:
  `sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46`.
- 8 حاويات Running وكل healthchecks المعرّفة سليمة. الحاويات الثماني
  `RestartCount=0` بعد القطع.
- PostgreSQL وRedis بقيا على volumes والحاويات طويلة العمر ولم يُعاد
  إنشاؤهما أثناء النشر.

## 3. DNS وTLS والـedge

سجلات Hostinger الفعالة:

| الاسم | النوع | القيمة | TTL |
|---|---|---|---:|
| `@` | A | `191.218.161.133` | 300 |
| `app` | A | `191.218.161.133` | 300 |
| `www` | CNAME | `elkheima.com` | 300 |

- authoritative nameservers:
  `pixel.dns-parking.com` و`byte.dns-parking.com`.
- authoritative DNS و`1.1.1.1` و`8.8.8.8` و`9.9.9.9` أعادوا عنوان
  الـVPS للجذر و`app`.
- Hostinger DNS rollback snapshot: `167902017`، أُنشئ
  `2026-07-30T03:18:09Z`، ويحفظ الحالة السابقة
  `@ A 2.57.91.91` و`www CNAME elkheima.com`.
- لم يُستخدم Reset DNS، ولم يُضف AAAA، ولم تُمس سجلات أخرى.
- شهادة Let's Encrypt ECDSA باسم `elkheima.com` تشمل:
  `elkheima.com`, `www.elkheima.com`, `app.elkheima.com`.
- الشهادة صالحة من `2026-07-30 02:21:35 UTC` حتى
  `2026-10-28 02:21:34 UTC`.
- `certbot renew --dry-run` وdeploy hook لإعادة تحميل Nginx نجحا.
- HSTS canary فعال بقيمة `max-age=604800` دون `includeSubDomains` في
  المرحلة الأولى.
- المنافذ العامة للتطبيق 80 و443 فقط؛ منفذ marketing القديم 8443 أُغلق.

## 4. فحص الإنتاج الخارجي

- `https://elkheima.com/` يعيد 200.
- `https://www.elkheima.com/` يعيد 200.
- `https://app.elkheima.com/` يعيد 200.
- `https://app.elkheima.com/health` يعيد 200 و`status=ok`.
- HTTP على النطاقات الثلاثة يعيد 301 إلى HTTPS الصحيح.
- HTML و`robots.txt` و`sitemap.xml` تحتوي الدومين الرسمي، وصفر مراجع
  للعنوان `191.218.161.133`.
- فحص marketing canary قبل الاستبدال: `/` و`/health` = 200،
  domain refs في 4 ملفات، old-IP refs = 0.
- Backend runtime origins هي الجذر و`www` و`app` فقط، وخريطة Chatbot
  العامة مقصورة على الجذر و`www`.
- Chatbot E2E من الدومين: welcome عربي، إنشاء session، قبول disclosure،
  رد Gemini عربي غير فارغ، وإنهاء session بنجاح.
- `/ar/timeshare` و`/en/timeshare` يعيدان 200. الصفحة تعرض Blue Bay كجهة
  إدارة الملكية الجزئية، وترسل الاستفسار إلى `/api/v1/hub/contact` مع
  consent وidempotency. لا تعرض أسعارًا أو تضمن توفرًا أو شروطًا تعاقدية.
- ترجمات Marketing متطابقة: 2919 مفتاحًا في كل من العربية والإنجليزية
  والروسية والإيطالية، وصور الأنشطة والفعاليات راجعها Codex بصريًا.
- تطبيق الموظفين المنشور يحتوي إصلاح تبديل المنفذ للطلب القائم: وجود
  `pendingOrderId` يغيّر المنيو دون إلغاء الطلب، أما السلة المحلية وحدها
  فتحتفظ بنافذة التأكيد. ملف `UnifiedPOSView` المنشور طابق البناء المحلي
  عند SHA-256
  `0339d0eb7ca8c93a9a9fa081d74e13c6b47a6bc78d9940bfa8b2a024388dea87`.
- فحص logs النهائي لخدمات backend/worker/beat/staff/marketing/nginx:
  صفر أنماط severe ضمن نافذة الفحص.

## 5. مسار الموظفين والحسابات المنشور

- الموارد البشرية (`hr_manager` أو الإدارة) تنشئ سجل الموظف داخل الفرع
  الفعال؛ لا تقبل نقطة الإنشاء `user_id` ولا تسمح للمحاسب بإدارة HR.
- السوبر أدمن يفتح مركز الإدارة الموحد، يختار سجل الموظف، ثم ينشئ حساب
  الدخول ويحدد الدور. Backend يربط الحساب بالموظف ويضيف عضوية الفرع
  الافتراضية الفعالة داخل transaction واحدة.
- إنشاء الحساب محمي بـStep-Up ومسجل في Audit. العزل بين الفروع fail-closed،
  ومسار الربط اليدوي القديم محصور في السوبر أدمن كاستعادة مدققة ولا يمنح
  عضوية فرع.
- صفحات المستخدمين والصلاحيات القديمة تحوّل إلى مركز السوبر أدمن بدل
  ازدواج الشاشات، والقائمة الجانبية منظمة إلى مجموعات تشغيلية مع عرض هاتف
  off-canvas.
- حسابات الموظفين العاديين، ومنها المحاسب، تُنشأ من هذا المسار بعد سجل HR.
  إنشاء `super_admin` احتياطي يبقى bootstrap من الطرفية فقط.

حالة الإنتاج بعد النشر: `users=1`, `active_superadmins=1`, `branches=1`,
`employees=0`, `active_memberships=1`. لم تُنشأ هويات أو كلمات مرور
تجريبية.

## 6. البيانات التجريبية المنشورة

البيانات synthetic وموسومة وليست اعتمادًا ماليًا أو تشغيليًا نهائيًا.
اقتصر التطبيق على الفرع الفعال الوحيد `ELK-001` وبهوية
`super_admin` الفعالة، مع advisory lock وdry-run افتراضي وconfirmation
صريح.

| النطاق | العدد |
|---|---:|
| المخازن / تصنيفات المخزون / المنتجات | 3 / 10 / 114 |
| حركات الرصيد الافتتاحي | 114 |
| الموردون / أوامر الشراء / طلبات الشراء | 6 / 5 / 3 |
| منافذ المطعم / الأصناف / مكونات الوصفات / الطاولات | 2 / 104 / 459 / 12 |
| أنواع الغرف / الغرف / خطط الأسعار | 5 / 52 / 4 |
| الأقسام / الأصول / أوامر الصيانة المغلقة أو الملغاة | 12 / 6 / 3 |
| عملاء CRM / leads / opportunities / campaigns | 4 / 4 / 2 / 1 |
| وحدات timeshare / عقود draft | 12 / 3 |
| عقود lease draft | 3 |
| مواقع beach تجريبية / عقود B2B غير فعالة | 8 / 2 |
| محتوى Hub | 3 صفحات draft + عرض inactive + مقال draft |

لم يضف importer مستخدمين أو كلمات مرور أو sessions أو صلاحيات، ولم يضف
حجوزات أو مدفوعات أو قيود يومية أو رواتب أو dining orders أو beach sales
أو أقساط أو guest alerts. ملفات العد قبل وبعد متطابقة byte-for-byte:

- `/var/backups/resort-os/source-releases/32eb0f8-pre-seed-counts.txt`
- `/var/backups/resort-os/source-releases/32eb0f8-post-seed-safety-counts.txt`

قراءة الإنتاج في آخر فحص أظهرت حسابًا واحدًا فقط:
`super_admin: total=1, active=1`. لا توجد سجلات أو حسابات موظفين حتى
الآن، ولم تُعرض أي بيانات اعتماد في التوثيق أو الفحص. إنشاء الحسابات ينتظر
أسماء وبريد وأدوار أشخاص حقيقيين، وفق `manual/02-دليل-الموظفين-والتدريب.md`.

## 7. أدلة الجودة

- full backend suite: 2181 passed و40 skipped من 2221 collected، صفر
  failure.
- production demo seed tests: 9 passed.
- PostgreSQL clean-schema apply + idempotency + safety checks: passed.
- استعادة dump حقيقية واختبار importer عليها ثم تنظيف DB المؤقتة: passed.
- onboarding/HR/auth focused backend: 228 passed و1 skipped؛ وآخر فحص
  أمني بعد تعديل الربط: 31 passed.
- frontend: 95/95 عبر 13 ملف اختبار.
- frontend type-check وproduction build: passed.
- full backend release regression: 2181 passed و40 skipped، صفر failure؛
  Alembic بقي عند head واحد `88d1c505a9dc`.
- Marketing `truth`, `type-check`, `build`: passed.
- `agent-check`: passed بعد تغييرات النشر؛ Alembic single head
  `88d1c505a9dc`؛ `git diff --check`: passed.
- دليل الإدارة وتدريب الموظفين العربي محدث، ودليل السوبر أدمن مصحح بحسب
  مسار إنشاء الحسابات و2FA وStep-Up الحالي.

## 7.1 CI مستقل حقيقي (GitHub Actions) — 2026-08-05

مراجعة Codex لـREL-07 كشفت إن الـCI مكنش شغال على الفرع التشغيلي خالص
(الـworkflow كان مقصور على `main`/`release/**` بس)، وإن آخر 7 تشغيلات على
`main` كانت كلها حمراء — بتفويض Mohamed الصريح ("نفّذ CI-01 + TEST-ENV-01 +
DOC-SYNC-01") اتفحصت اللوجات الفعلية (مش تخمين) واتصلحت الأسباب الجذرية:

- Redis غايب كـservice في الـCI (اتصال مرفوض على `localhost:6381` كان
  بيكسر أي تست بينادي Celery `.delay()`، وبيتسرّب لتستات تانية مش متعلقة).
- `pdftotext` (poppler-utils) غير مثبّت — تستات إيصالات الإيجار بتتأكد من
  محتوى PDF الفعلي بيه.
- `DB_PASSWORD` غير معرّف وقت فحص `docker-compose.prod.yml` (compose
  بيرفض المتغيّر الإجباري ده زي الإنتاج الحقيقي بالظبط).
- `backend/.env.prod` (مطلوب كـ`env_file:` في compose نفسه) مش موجود في
  checkout نضيف خالص — لازم ملف فاضي CI-only.
- الفرونت إند كان بيشغّل `test:unit` (بس `vitest run`) بدل `test:frontend`
  الرسمية (بتضيف فحص تطابق مفاتيح i18n عربي/إنجليزي).

**التغييرات**: `.github/workflows/ci.yml` — إضافة الفرع + `workflow_dispatch`،
`redis:7-alpine` service على نفس المنفذ اللي `.env.example` بيتوقعه، تثبيت
`poppler-utils`، قيم CI وهمية ثابتة (≥32 حرف، بدون كلمات ضعيفة) لـ
`SECRET_KEY`/`SURVEY_TOKEN_SECRET`/`TIMESHARE_PORTAL_TOKEN_SECRET`، فحص
Alembic single-head جديد، `touch backend/.env.prod` قبل فحص prod compose،
`DB_PASSWORD` وهمي، `test:frontend` بدل `test:unit`.

**دليل تشغيل حقيقي أخضر بالكامل** (مش تعديل ملف بس — تشغيل فعلي اتأكد منه):

- Resort OS commit `99bab4a`: run
  [30962088781](https://github.com/wego2388/Resort-OS/actions/runs/30962088781)
  — Backend/Frontend/Docker-Config كلهم ✅ (2246 passed، 12 skipped، صفر
  failure).
- Marketing commit `f27aa63`: run
  [30960931242](https://github.com/wego2388/elkheima-marketing-website/actions/runs/30960931242)
  — public-truth + type-check + build ✅.
- **ملاحظة توثيقية مهمة**: تشغيلتين سابقتين على نفس commit تقريبًا (قبل
  `99bab4a`) طلعوا بـ28 فشل — كلهم في تستات مبنية على `date.today()`/
  `business_today()` (فروع، مخزون شاطئ، تكلفة طعام، شيكات...)، والسبب
  اتأكد إنه توقيت التشغيل نفسه عدّى منتصف ليل UTC فعليًا أثناء الـ~5.5
  دقيقة تشغيل التستات (`assert '2026-08-05' == '2026-08-04'` حرفيًا في
  اللوج) — مش regression حقيقي من تعديلات الـCI. اتأكد بإعادة تشغيل بعيد
  عن الحد بدقايق كتير ورجعوا كلهم أخضر بنفس الـcommit بالظبط. **فجوة
  حقيقية منفصلة موثّقة هنا للمستقبل**: التستات دي مش freeze للوقت
  (زي `freezegun`)، فأي تشغيل CI يصادف منتصف الليل UTC حرفيًا معرّض لنفس
  الفلاكينس دي — تحسين مستقبلي محتمل، مش حاجز حاليًا.
- `elkheima-marketing-website` مكانش فيه أي CI خالص قبل كده — workflow
  جديد بالكامل (`f27aa63`)، أول تشغيل حقيقي طلع أخضر مباشرة.

## 8. النسخ والتراجع

- DNS rollback: Hostinger snapshot `167902017`.
- domain-cutover rollback directory:
  `/var/backups/resort-os-domain-cutover-aed94a0`، mode `0700`.
- يحتوي image manifest، SHA لنسخة DB، ونسخة مشفرة الصلاحيات من إعدادات
  Let's Encrypt السابقة وملفات systemd السابقة.
- Resort base cutover archive:
  `/var/backups/resort-os/source-releases/aed94a0.tar.gz`،
  SHA-256
  `eb404ef2341e6ca10ff658d00dc2846d6daf81cdd5589d98343c4c1e5bccca72`.
- صور ما قبل cutover محفوظة تحت
  `resort-os-rollback/*:pre-domain-aed94a0`.
- صورة Marketing السابقة محفوظة تحت
  `resort-os-rollback/marketing-site:pre-e5e122a`
  (`sha256:014777142d8cae6074b13dfee5493f5e7e08f6901797164104292a1b05121c5b`).
- صورة Marketing السابقة مباشرة لـ`16f8f2c` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-16f8f2c`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/16f8f2c-rollback-image.txt`.
- صورة Marketing السابقة مباشرة لـ`0b0321f` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-0b0321f`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/0b0321f-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/16f8f2c` لسه موجود كامل
  على القرص، مش متحذوف. لا migration ولا تغيير DB في هذه الحزمة (frontend
  فقط) فمفيش نسخة DB مخصوصة ليها.
- أرشيف إصدار Marketing `4fba5b6` (حدود إدخال استمارة استبيان الضيف):
  `/var/backups/resort-os/marketing-source-releases/4fba5b6.tar.gz`،
  SHA-256
  `81018ef5e29577bfeb40c2a299dd37d12b8cf2433c4946a6798cf7b5e83bf641`.
- صورة Marketing السابقة مباشرة لـ`4fba5b6` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-4fba5b6`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/4fba5b6-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/0b0321f` لسه موجود كامل
  على القرص، مش متحذوف. لا migration ولا تغيير DB في هذه الحزمة برضو.
- أرشيف إصدار Marketing `53bf7a3` (idempotency + بوابات PUBLIC_TRUTH +
  توجيه اللغة عبر باقي شاشات الموقع):
  `/var/backups/resort-os/marketing-source-releases/53bf7a3.tar.gz`،
  SHA-256
  `6e216b8ae15fda2efcda6d16e3819df9b3cbacb7c07a866c70110aec32962f6a`.
- صورة Marketing السابقة مباشرة لـ`53bf7a3` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-53bf7a3`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/53bf7a3-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/4fba5b6` لسه موجود كامل
  على القرص، مش متحذوف. لا migration ولا تغيير DB في هذه الحزمة برضو.
- أرشيف إصدار Marketing `1371975` (MKT-06 — إصلاح سكرول أفقي عربي فقط في
  /contact):
  `/var/backups/resort-os/marketing-source-releases/1371975.tar.gz`،
  SHA-256
  `21fbf305bc06e038464803e1c51703a3b7bcc899e97acfcc35717ac1b061b903`.
- صورة Marketing السابقة مباشرة لـ`1371975` محفوظة تحت
  `resort-os-rollback/marketing-site:pre-1371975`، والـmanifest:
  `/var/backups/resort-os/marketing-source-releases/1371975-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/53bf7a3` لسه موجود كامل
  على القرص، مش متحذوف. لا migration ولا تغيير DB في هذه الحزمة برضو.
- النسخة المشفرة خارج الخادم واستعادة 135 جدولًا ما زالتا دليل DR الأساسي.
- `resort-os-backup.timer`, `resort-os-certbot-renew.timer`,
  `resort-os-healthcheck.timer` مثبتة ومفعلة.
- أرشيف الإصدار الحالي:
  `/var/backups/resort-os/source-releases/a3e8abb.tar.gz`،
  SHA-256
  `2ff370284727ae57688c4efda9dad22db2729abf45fbbfe3dc276e78d7388bad`.
- صور ما قبل `a3e8abb` محفوظة تحت
  `resort-os-rollback/*:pre-a3e8abb`، والـmanifest المحمي:
  `/var/backups/resort-os/source-releases/a3e8abb-rollback-images.txt`،
  SHA-256
  `f904b6922081b17630814893708e39a543614d8652c2ce974922ec0fbd8f8fec`.
- نسخة DB السابقة مباشرة لنشر إصلاح الـPOS:
  `/var/backups/resort-os/database/resort_os_20260731_210536.dump`،
  SHA-256
  `5dd553f00433f0d7b70e3fcd54518c3c0c1770494efe6c4429dbd2858720aa1d`؛
  اجتازت `pg_restore --list`.
- نسخة DB السابقة مباشرة للقطع:
  `/var/backups/resort-os/database/resort_os_20260730_062529.dump`،
  SHA-256
  `bce5553a9b58d7a930c650c3f8618b7714a9a1db557e067977cc23beec10ab5a`؛
  اجتازت `pg_restore --list`.
- نسخة DB السابقة مباشرة لنشر Marketing:
  `/var/backups/resort-os/database/resort_os_20260730_143944.dump`،
  SHA-256
  `1358f16a526240b447bff98570a93eda9ee8933d8a94580ee5e8ec12c3987e04`؛
  اجتازت `pg_restore --list`.
- شُغلت خدمة healthcheck يدويًا بعد النشر ونجحت
  (`Result=success`, `ExecMainStatus=0`).
- أزيل فقط release staging غير الفعال
  `/opt/resort-os-releases/0b430fb` بعد إثبات عدم وجود symlink أو container
  يشير إليه. أرشيفه القابل للاستعادة ما زال محفوظًا تحت
  `/var/backups/resort-os/source-releases/0b430fb.tar.gz`.
- أرشيف إصدار `ddfbaaa` (دعم الطلب متعدد المنافذ + إصلاح مرتجع الإيراد):
  `/var/backups/resort-os/source-releases/ddfbaaa.tar.gz`،
  SHA-256
  `8aafedfd109a59e7ed72ea2c4ecc30b248d51af63f09198d0b0cd1629c1390d6`.
- صور ما قبل `ddfbaaa` (backend/celery_worker/celery_beat/el_kheima، كلها
  كانت `679f76e`) محفوظة تحت `resort-os-rollback/*:pre-ddfbaaa`، والـmanifest:
  `/var/backups/resort-os/source-releases/ddfbaaa-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `ddfbaaa`:
  `/var/backups/resort-os/database/resort_os_20260802_031105.dump`،
  SHA-256
  `7f65646441948e4250b9f141f6d01855e5516794507626eb09d5ebe4d97fd238`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `4a0a777` (إصلاح ضريبة الدخل في الرواتب، `backend`/
  `celery_worker`/`celery_beat` بس — `el_kheima` من `ddfbaaa` لم يتغيّر):
  `/var/backups/resort-os/source-releases/4a0a777.tar.gz`،
  SHA-256
  `a2638b2a0609cc3931e5e379a28e60823c5886b2213c472419672223227c6405`.
- صور ما قبل `4a0a777` (backend/celery_worker/celery_beat، كانوا `ddfbaaa`)
  محفوظة تحت `resort-os-rollback/*:pre-4a0a777`، والـmanifest:
  `/var/backups/resort-os/source-releases/4a0a777-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `4a0a777`:
  `/var/backups/resort-os/database/resort_os_20260802_034252.dump`،
  SHA-256
  `85f5e5fe300b5f90d49993bc820793e5e5258a2fb37ee35f663efb4784c5f8e7`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `8597535` (إصلاح باج تزامن استرداد نقاط الولاء في CRM،
  `backend`/`celery_worker`/`celery_beat` بس — `el_kheima` من `ddfbaaa`
  لم يتغيّر، صفر migration):
  `/var/backups/resort-os/source-releases/8597535.tar.gz`،
  SHA-256
  `4fcd0da28a3dd6067820315445755be6fcf31beab15114e961e7b5a2c1658320`.
- صور ما قبل `8597535` (backend/celery_worker/celery_beat، كانوا `4a0a777`)
  محفوظة تحت `resort-os-rollback/*:pre-8597535`، والـmanifest:
  `/var/backups/resort-os/source-releases/8597535-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `8597535`:
  `/var/backups/resort-os/database/resort_os_20260802_103152.dump`،
  SHA-256
  `5ecad84360934af560b617c25cdfa53b3730218342e1bce3f5e098b12196ebdc`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `b1db886` (موديول الصيانة: منع إغلاق أمر "مكتمل" عبر PATCH
  العادي + ربط تحرير الأصل بمسار الإلغاء — `backend`/`celery_worker`/
  `celery_beat`/`el_kheima` الأربعة، صفر migration):
  `/var/backups/resort-os/source-releases/b1db886.tar.gz`،
  SHA-256
  `da2bb917b3e7646c5635a4be8fe9edcfc5d80301a477385b93264d17b87cc36a`.
- صور ما قبل `b1db886` (backend/celery_worker/celery_beat/el_kheima، كانوا
  `8597535`/`ddfbaaa` بالترتيب) محفوظة تحت `resort-os-rollback/*:pre-b1db886`،
  والـmanifest: `/var/backups/resort-os/source-releases/b1db886-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `b1db886`:
  `/var/backups/resort-os/database/resort_os_20260802_105621.dump`،
  SHA-256
  `b838604a4db79f02dc099cfc2ef674eab0b6bc34364f2f344c10631cd8ffe472`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `0d55717` (موديول التحليلات: تحقق صارم على مدخلات تقييم
  الضيف العام — `backend`/`celery_worker`/`celery_beat` بس، `el_kheima`
  لم يتغيّر، صفر migration):
  `/var/backups/resort-os/source-releases/0d55717.tar.gz`،
  SHA-256
  `ba9788b147e44c0b19f03edd5541acfb54744d576a89cab71d249fba7ca3fc21`.
- صور ما قبل `0d55717` (backend/celery_worker/celery_beat، كانوا
  `b1db886`) محفوظة تحت `resort-os-rollback/*:pre-0d55717`، والـmanifest:
  `/var/backups/resort-os/source-releases/0d55717-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `0d55717`:
  `/var/backups/resort-os/database/resort_os_20260802_111432.dump`،
  SHA-256
  `c07404cc07489f3cd774938986db269ea5556f657a508ecf1cd4a0090979fa3a`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `4ca10c1` (موديول الإيجارات: تحصيل إيجار على عقد مفسوخ/
  منتهي عبر التسوية الكاش اليومية بقى مرفوض زي التحصيل العادي —
  `backend`/`celery_worker`/`celery_beat` بس، `el_kheima` لم يتغيّر، صفر
  migration):
  `/var/backups/resort-os/source-releases/4ca10c1.tar.gz`،
  SHA-256
  `e6c73575e7020a5676b6233777808211b0979bf55f87be1f986150ac9c945906`.
- صور ما قبل `4ca10c1` (backend/celery_worker/celery_beat، كانوا
  `0d55717`) محفوظة تحت `resort-os-rollback/*:pre-4ca10c1`، والـmanifest:
  `/var/backups/resort-os/source-releases/4ca10c1-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `4ca10c1`:
  `/var/backups/resort-os/database/resort_os_20260802_113200.dump`،
  SHA-256
  `d74442b6b78e52dd721b35b8427f6af0a354ef3e8f49fa61a2021e123418b870`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `5b02010` (موديول Hub: حذف كود مكرر كان بيسبب
  UnboundLocalError صامت في تأكيد الحجوزات الأونلاين — `backend`/
  `celery_worker`/`celery_beat` بس، `el_kheima` لم يتغيّر، صفر migration):
  `/var/backups/resort-os/source-releases/5b02010.tar.gz`،
  SHA-256
  `50538820d9b9e4ef9e3d724e45b09dfca4dfc86e25154a852fab98765900b673`.
- صور ما قبل `5b02010` (backend/celery_worker/celery_beat، كانوا
  `4ca10c1`) محفوظة تحت `resort-os-rollback/*:pre-5b02010`، والـmanifest:
  `/var/backups/resort-os/source-releases/5b02010-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `5b02010`:
  `/var/backups/resort-os/database/resort_os_20260802_115042.dump`،
  SHA-256
  `f2547e1b089c7e9706931536218be92868faf4622f0519e60c6870e364330f91`؛
  اجتازت `pg_restore --list` (تحقّق فعلي داخل حاوية الـDB نفسها).
- أرشيف إصدار `821a718` (23 commit — راجع القسم 2 أعلاه للنطاق الكامل؛
  `backend`/`celery_worker`/`celery_beat`/`el_kheima`/`marketing_site`
  (سياق بدون تغيير مصدر) اتبنوا واتنشروا كلهم، 4 migrations):
  `/var/backups/resort-os/source-releases/821a718.tar.gz`،
  SHA-256
  `542cdaa35f7dfb6ae1dd6da68c825d65954da2606a57783ff177c479f35a4411`.
- صور ما قبل `821a718` (backend/celery_worker/celery_beat/el_kheima/
  marketing_site/nginx، كانوا `5b02010`) محفوظة تحت
  `resort-os-rollback/*:pre-821a718`، والـmanifest:
  `/var/backups/resort-os/source-releases/821a718-rollback-images.txt`.
- نسخة DB السابقة مباشرة لنشر `821a718`:
  `/opt/resort-os-releases/5b02010/backups/resort_os_20260803_232155.dump`،
  SHA-256
  `e9eff9a27f3d81403de4f7589d385a4c5bdaebb141b19d297fe27e8852f1969b`؛
  اجتازت `pg_restore --list` (1373 TOC entries، تحقّق فعلي داخل حاوية
  الـDB نفسها).

## 8.1 فجوة محاسبية — تسوية فوليو الـcheckout ما بتشملش الشحنات الإضافية
المحمّلة على الغرفة (شاطئ/دايننج) — **✅ اتصلحت REL-12 (2026-08-09)**

> **الحالة**: اتصلحت فعليًا ومنشورة (commit `403bbd7`، راجع REL-12 فوق) —
> محمد أكّد صراحةً "الاستقبال بيحصّل كل حاجة مرة واحدة وقت الخروج"،
> فالتسوية بقت تشمل كل شحنات beach/dining على الفوليو مش سعر الغرفة بس.
> القسم ده باقٍ كتوثيق تاريخي للاكتشاف الأصلي والتحليل الكامل.

**اتكتشفت 2026-08-09 أثناء مراجعة PMS + Beach النهائية — قرار Mohamed مطلوب
قبل أي إصلاح، مش bug عشوائي يتصلح لوحده.**

**آلية القيود الحالية (كل جزء منها صحيح لوحده، المشكلة في التجميع النهائي):**

1. **إيراد الغرفة نفسه**: بيترحّل يوميًا عبر Night Audit
   (`pms.services._post_room_revenue_for_night_audit`، بتنادى من
   `run_night_audit`) — Dr.1150 (ذمم الفوليو) / Cr.4100 (إيراد الغرف) —
   لكل ليلة إقامة فعلية، بناءً على `BookingRoom.daily_rate`. **القيد ده
   مالوش أي `FolioCharge` مقابل** — بيترحّل مباشرة كـJournalEntry بس، من
   غير أي أثر في جدول `folio_charges`.

2. **الشحنات الإضافية المحمّلة على الغرفة** ("Charge to Room" — تذكرة
   شاطئ أو فاتورة مطعم/كافيه أثناء الإقامة): بتتسجّل كـ`FolioCharge`
   حقيقي على `Folio` الحجز (`Booking.folio_id`) + قيدها الخاص وقت
   الشحن نفسه (Dr.1150 / Cr.4300 للشاطئ عبر
   `beach.services._post_beach_folio_charge_journal`، أو Cr.4200/4400
   للدايننج عبر `dining.services` مسار مشابه) — و`Folio.total` بيتحدّث
   تلقائيًا (`finance.crud.recalculate_folio_total`) ليعكس مجموع كل
   `FolioCharge` المرتبطة.

3. **تسوية الـcheckout**: `pms.services._post_checkout_journal` (تُنادى من
   `checkout_booking`) بترحّل Dr.نقدية/بنك (حسب `booking.payment_method`)
   / Cr.1150 — لكن **بمبلغ `booking.total_rate` بس** (سعر الغرفة/الليالي
   المحجوزة)، **مش `Folio.total`** (اللي بيشمل أي شحنات إضافية زي فوق).

**النتيجة العملية**: لو ضيف حجز حاجات على حساب غرفته (تذكرة شاطئ/فاتورة
مطعم) أثناء إقامته، القيد الوحيد اللي بيسوّي حساب 1150 عند الـcheckout
بيغطي سعر الغرفة بس — **رصيد الشحنات الإضافية يفضل قايم على حساب "ذمم
الفوليو" (1150) للأبد بعد الـcheckout، بصمت، من غير أي خطأ ظاهر** (مفيش
استثناء، مفيش تنبيه — العملية التشغيلية بتنجح 100% دايمًا). ميزان
المراجعة (trial balance) هيفضل فيه رصيد متضخّم تراكميًا في 1150 بمرور
الوقت كل ما ضيف يشحن حاجة على غرفته.

**ليه معملتش حاجة**: القرار الصح هنا محتاج مدخل من محمد، مش قرار هندسي
منفرد — فيه أكتر من طريق ممكن:
- تسوية `Folio.total` كامل بدل `booking.total_rate` (لو الاستقبال فعليًا
  بيحصّل كل حاجة مرة واحدة عند الخروج).
- أو سياسة تانية لو الشحنات الإضافية بتتحصّل بشكل منفصل تشغيليًا (مثلاً
  تحصيل فوري وقت الشحن نفسه لبعض الحالات) — يحتاج توضيح الواقع التشغيلي
  الفعلي في المنتجع قبل أي كود.
- **لا يوجد backfill رجعي مقترح** لأي حجز اتعمله checkout قبل التوثيق ده
  (نفس سياسة عدم الـbackfill الموثّقة في CLAUDE.md §18 لفجوات مشابهة —
  cost_center_id، خصم السلف).

**النطاق المؤكد**: راجعت كل الـ`FolioCharge` sources (`beach`, `dining`)
+ `_post_checkout_journal` + `_post_room_revenue_for_night_audit` مباشرة
من الكود، مش افتراض — الفجوة حقيقية ومؤكدة، مش نظرية.

## 8.2 فجوات UI مؤجَّلة (ميزات Backend كاملة بدون شاشة) — 2026-08-09

اكتشفت أثناء نفس الجولة، **مؤجّلة عمدًا** (أولوية §2 #2 "تنضيج الموديولات
الموجودة"، مش bug زيرو-تسامح، ومفيش قرار Mohamed صريح عليها لسه):

| الميزة | Backend | Frontend |
|---|---|---|
| جدول العمل (Rota) — templates/assignments/swap requests | ✅ كامل | ❌ مش موجود في `HRView` |
| إغلاق الفترة المحاسبية (`POST /finance/periods/{y}/{m}/close`) | ✅ | ❌ مفيش UI في `FinanceView` |
| عرض الفترات المحاسبية (`GET /finance/periods`) | ✅ | ❌ مفيش UI |
| Barcode Labels (`GET /inventory/products/barcode-labels`) | ✅ | ❌ مش في `InventoryView` |
| Fraud tasks (`app/tasks/fraud_tasks.py`، راجع Batch 3 أعلاه) | ✅ | لا يظهر تنبيه/سجل في أي شاشة إدارية |

كمان: i18n keys الناقصة بتظهر كـraw key في الواجهة من غير أي validation
تلقائي وقت الـbuild — تحسين مستقبلي، مش أولوية.

## 9. الحالة المتبقية

| الحزمة | الحالة |
|---|---|
| REL-04 — staff-control-plane deploy | COMPLETE |
| REL-05 — multi-outlet POS fix deploy | COMPLETE |
| DATA-01-DEMO — realistic synthetic dataset | COMPLETE |
| CHAT-01 — chatbot activation/live verification | COMPLETE |
| DNS-01 — domain/TLS cutover | COMPLETE |
| DOC-OPS — management/staff Arabic training guide | COMPLETE |
| ACC-01 — employee/account workflow | DEPLOYED؛ ACCOUNTS PENDING ROSTER |
| UAT-01 — device/roles/workflow acceptance | PENDING |
| DATA-02 — approved real master data | PENDING OWNER/OPERATIONS REVIEW |
| OPS-01 — monitoring and burn-in | BASELINE COMPLETE؛ external delivery pending |
| provider snapshot | RECOMMENDED؛ DNS snapshot وoff-server DB موجودان |

لا توجد مشكلة تطبيق أو DNS أو TLS معروفة تستوجب rollback. لا يعني ذلك
اعتماد العمليات أو المالية؛ UAT والبيانات الحقيقية وقرار Go/No-Go تظل
مسؤولية المالك وممثلي التشغيل.
