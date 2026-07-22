# Gate 4 — Dining Payment, Shift & Order Integrity

**الحالة الحالية (مراجعة مستقلة نهائية 2026-07-22):** Gate 4 نُفِّذت
ودُمجت في worktree الإصدار مع Gate 8، واتعملت مراجعة مستقلة للكود والعقود
المالية والصلاحيات قبل بدء Gate 9. المراجعة كشفت ملاحظات إضافية حقيقية؛
كلها اتصلحت واختبارات الانحدار الخاصة بها خضراء. لا يوجد commit أو push أو
نشر جديد من worktree المراجعة الحالية.

الهدف (من عقد التنفيذ `docs/audits/gate-4-execution-brief.md`): تحويل رحلة
Dining من «الطلب يمكن أن يصبح paid» إلى عقد مالي/تشغيلي قابل للإثبات — كل تحصيل
يظهر مرة واحدة، منسوبًا للكاشير والوردية والطريقة والطلب؛ split/refund/void لا
تترك أثرًا جزئيًا أو مكررًا؛ ولا يمكن فتح طلبين لنفس الطاولة أو ورديتين لنفس
الكاشير بسبب سباق.

## مراجعة ما قبل Gate 9 — النتائج والتصحيحات (2026-07-22)

- **High — خلط أصناف بين المنافذ/الفروع:** `add_items_to_order` كان يقبل
  `item_id` صالحًا حتى لو تابعًا لمنفذ أو فرع آخر، فيشوّه السعر والمخزون
  ونسبة الإيراد. أصبح التحقق server-side يفرض تطابق الفرع والمنفذ مع الطلب.
- **High — دمج الطلبات كان يكسر السجل المالي والتشغيلي:** التنفيذ السابق كان
  يجمع `total` فقط، ولا يعيد حساب subtotal/VAT/service/discount، ولا ينقل
  تذاكر KDS، ولا يمنع الدمج بين منفذين. التنفيذ الحالي يقفل الطلبين بترتيب
  حتمي، يقبل فقط طلبات صالة نشطة في نفس الفرع والمنفذ ونفس customer/folio/
  guest-session context، ينقل الأصناف والتذاكر الموجودة، يعيد بناء كل
  الإجماليات، يحرر الطاولة الثانوية، ويكتب AuditLog كاملًا.
- **High — أصناف حية كانت قد تضيع خارج KDS:** إضافة صنف إلى طلب
  `in_kitchen/served`، أو دمج طلب `open` في طلب دخل المطبخ، لم يكن يضمن
  ticket للصنف الجديد. أصبح helper واحد ينشئ تذاكر للمحطات وللأصناف الناقصة
  فقط بلا تكرار التذاكر الحالية، ويعيد `served` إلى `in_kitchen` عند وجود
  صنف pending جديد. الدمج يبث تحديث KDS والطاولتين لحظيًا، ولا يدّعي
  `served` بينما جزء من الطلب ما زال مفتوحًا.
- **High — أكثر من tender غرفة غير قابل للعكس بأمان:** نموذج المرتجع الحالي
  يربط الطلب بفوليو واحد؛ قبول أكثر من tender غرفة كان يسمح بتسوية لا يستطيع
  مسار المرتجع عكسها على كل الفوليوهات. أصبح المسار fail-closed ويرفض أكثر
  من tender غرفة حتى يوجد نموذج multi-folio مكتمل.
- **Medium — canonical hash غير آمن للأنواع المختلطة:** ترتيب tuples فيها
  `None` وroom id رقمي كان قد يرفع `TypeError` قبل التسوية. أصبح intent
  canonical JSON بترتيب حتمي لا يقارن أنواع Python غير المتجانسة.
- **High — KDS وقراءة الطلب/الإيصال ناقصها عزل فرع:** قراءة الطلب، الإيصال،
  قائمة/تحديث KDS، وWebSocket للطاولات/KDS أصبحت تستخدم
  `assert_branch_access` (super_admin فقط يتخطى). اختبارات cross-branch تثبت
  403، وWebSocket يغلق 4403.
- **High — تحديث KDS كان يتسابق مع الدفع:** تحديث صنف أو تذكرة كاملة أصبح
  يقفل صف الطلب بنفس NOWAIT/409، ويعيد فحص أن الطلب ما زال نشطًا؛ لا يمكن
  تغيير حالة التحضير بعد paid/cancelled/refunded.
- **Medium — تقريب المرتجعات الجزئية:** آخر صنف مرتجع يأخذ الرصيد المتبقي
  بالضبط، فيضمن أن مجموع العكوس يساوي `order.total` ولا يترك/يتجاوز قرشًا
  بسبب التقريب النسبي.

**قرار محافظ موثّق:** multi-room tender مرفوض حاليًا بدل تخمين توزيع المرتجع.
هذا ليس نقصًا صامتًا؛ إضافة multi-folio settlement/refund لاحقًا تحتاج عقد
بيانات وواجهة واختبارات مستقلة.

### التحقق النهائي بعد مراجعة 22 يوليو

- Backend الكامل: `.venv/bin/pytest tests/ -v` → **2046 passed، 33 skipped،
  صفر failure من 2079**. الـskips هي اختبارات PostgreSQL التي تحتاج DSN غير
  موجود في بيئة المراجعة الحالية؛ لذلك لا ندّعي إعادة تشغيل دليل التزامن الحي
  في هذه الجولة، وتظل نتائجه التاريخية الموثقة أدناه دليلًا سابقًا فقط.
- اختبارات Dining المركزة: `test_dining.py` → **69 passed**،
  `test_dining_http.py` → **36 passed**، و`test_pos_full_cycle_http.py` →
  **2 passed**.
- Frontend: `type-check:all` نجح، `test:frontend` → **69 passed من 9
  ملفات**، و`build:all` نجح للتطبيقين. تطابق ar/en = **5710 مفتاح لكل لغة**
  وسياسة Public ذات الأربع لغات سليمة.
- قاعدة البيانات: `alembic heads` → رأس واحد
  `8c12d9e4f6a1 (head)`.
- ملاحظة غير مانعة قبل Gate 9: build ما زال يحذر من chunks أكبر من 500KB
  (Public نحو 910KB وStaff نحو 679KB قبل gzip). يلزم رصد الأداء الفعلي على
  staging، لكنه لا يغيّر صحة Gate 4 المالية.

**حدود الاعتماد:** مراجعة الكود والاختبارات الآلية مكتملة، لكن بدء Gate 9
يظل مشروطًا بقبول Gate 8 الميداني على هاتف/QR وشبكة حقيقية وstaging، وبإعادة
تشغيل اختبارات PostgreSQL الحية في بيئة ما قبل النشر.

نُفِّذت في ثلاث شرائح داخل حزمة واحدة (4A ثم 4B ثم 4C).

---

## Preflight (قراءة فقط، قبل أي تعديل بيانات)

شُغِّل استعلام read-only على قاعدة التطوير قبل أي migration. النتيجة:

- **صفر** duplicate active orders لكل طاولة.
- **صفر** duplicate open shifts لكل (branch, cashier).
- **صفر** shifts بلا cashier.
- **17** طلب Dining مدفوع (كاش مباشر، بلا فوليو) **بلا صف Payment** — دي بيانات
  تطوير تاريخية بتعكس بالظبط الفجوة اللي Gate 4 بيسدّها (الدفع المباشر ماكانش
  بينشئ Payment قبل كده). **مش** بيانات متعارضة تحتاج حذف/دمج: العقد يمنع
  backfill لكاشير/وردية مجهولة، فدي بتتسرد في تقرير reconciliation
  (`scripts/gate4_reconciliation.py`) بدل اختراع نسبة. الـ migration إضافية
  بالكامل ومابتفشلش عليها (كلها `paid`، خارج الـ partial unique index).
- **صفر** طرق دفع مجهولة (القيم الفعلية: cash/card/None فقط).

**لا preflight blocker.** التنفيذ استمر تلقائيًا عبر الشرائح الثلاث.

---

## Gate 4A — Settlement ledger & exactly-once payment

### ما كان موجودًا وأعيد استخدامه
- `_mark_order_paid` (Gate 1B) كان atomic بالفعل بالنسبة لحالة الطلب/الفوليو/
  المخزون/القيد ويقفل Order/Folio/Product — أعيد استخدام كل ده.
- `finance.crud.create_direct_payment` + `get_open_shift` (نمط beach) — نفس
  البنية التحتية اللي beach بيستخدمها لنسب البيع المباشر للوردية.
- قفل صف الطلب `get_order_for_update` (NOWAIT) و`add_folio_charge` (قفل الفوليو).

### Root causes المؤكدة
- دفع Dining المباشر ماكانش بينشئ `finance.Payment` ولا يعرف cashier/shift →
  بيع Dining كان غايب تمامًا عن تقرير الوردية.
- `payment_method` نص واحد بلا idempotency، وبلا تمثيل split tenders.
- `split_bill` مسار موازٍ: مايستخدمش وحدة العمل الصارمة، مايقفلش الطلب،
  مابينشئش Payment، وبيرحّل قيد إيراد كامل ممكن يكرر حصة الغرفة.
- القيد المحاسبي للبيع المباشر كان دايمًا Cash `1100` حتى لو card/wallet.

### التصميم كما نُفِّذ
- **`settle_order`** service primitive واحدة — المسار **الوحيد** لتحويل طلب
  لـ paid، سواء tender واحد (paid) أو أكتر (split). `_mark_order_paid`
  و`split_bill` بقوا wrappers رفيعة عليها. commit واحد؛ أي فشل rollback كامل.
- **جدول `dining_settlements`** جديد (مش تكرار لـ Payment — هو الأب المنطقي
  لصفوف الـ tenders): `UNIQUE(order_id)` = تسوية واحدة لكل طلب؛
  `UNIQUE(branch_id, idempotency_key)` جزئي = بوابة idempotency على مستوى الـ
  DB؛ `intent_hash` (sha256 للـ tenders المرتبة) = نفس المفتاح بنية مختلفة
  يترفض 409.
- **Idempotency contract:** `Idempotency-Key` header اختياري على paid/split.
  نفس المفتاح + نفس النية = replay بيرجّع نفس النتيجة (بلا أثر جديد). نفس
  المفتاح + نية مختلفة = 409 `IDEMPOTENCY_KEY_CONFLICT`. مفتاح مختلف على طلب
  مدفوع = 409 `ORDER_ALREADY_PAID`. الحماية في DB (partial unique index + قفل
  صف الطلب)، مش memory.
- **كل tender مباشر → `Payment` واحد** (`create_direct_payment`) منسوب
  للكاشير/الوردية/الطريقة/المبلغ/الطلب، مع `source='dining'`.
- **طريقة دفع typed fail-closed** (`dining/payment_policy.py`): cash→`1100`،
  room→ذمم `1150` (شحنة فوليو). card/wallet **لا تُربط بحساب مخترَع** — لازم
  حساب مقاصّة مهيّأ صراحةً (`DINING_CARD_SETTLEMENT_ACCOUNT`/
  `DINING_WALLET_SETTLEMENT_ACCOUNT`)، وإلا تفشل 503 `METHOD_NOT_CONFIGURED`.
- **الدفع المباشر يتطلب وردية مفتوحة** لنفس الكاشير والفرع (409
  `NO_OPEN_SHIFT`). الإنفاذ بيتفعّل كل ما فيه كاشير مسدِّد (settled_by) — وده
  **دايمًا** صحيح على مسار الإنتاج الوحيد (الراوتر بيفرض كاشير+ ويمرّر
  `user.id`)، فالـ invariant مضمون إنتاجيًا بالكامل. `settled_by=None` (نداء
  داخلي بلا actor، مش مسار HTTP) بيسجّل الـ tender بلا نسبة وردية بدل رفض
  «كاشير بلا وردية» وهو مفيش كاشير أصلاً.
- **allocation:** مجموع الـ tenders = `order.total` بدقة Decimal (± 0.01
  تقريب واحد). الإيراد المرحَّل = `order.total` بالظبط (حصة الغرفة عبر شحنة
  فوليو + قيد Dr 1150/Cr إيراد؛ الحصة المباشرة عبر Dr <حساب الطريقة>/Cr إيراد).

### Transaction / lock order (settle_order)
`get_order_for_update` (NOWAIT، 409 لو مشغول) → idempotency guard → فحص
الحالة/الإجمالي/الـ allocation → حل طرق الدفع fail-closed → قفل الوردية
(`get_open_shift`) للـ tenders المباشرة → حل فوليوهات الغرفة → تحديث حالة الطلب
والطاولة → شحنات الفوليو + Payment لكل tender + القيود → خصم المخزون (strict) →
زيارة العميل → صف `DiningSettlement` → commit واحد.

---

## Gate 4B — Shift locking & cash reconciliation

### Root causes
- `open_shift` check-then-insert بلا DB invariant → طلبان متزامنان يفتحوا
  ورديتين.
- `close_shift` مايقفلش صف الوردية → إغلاقان متزامنان يكتبوا count/variance
  مرتين.
- `expected_cash = opening_float + cash payments` فقط — CashMovement مش داخل.
- shift endpoints تقبل `branch_id` من العميل وبعضها بلا `assert_branch_access`.

### التصميم كما نُفِّذ
- **partial unique index `uq_open_shift_per_branch_cashier`** (على
  `status='open'`) — منع فتح مزدوج على مستوى الـ DB. `open_shift` بيمسك
  `IntegrityError` ويرفعها `OpenShiftConflictError` → 409 `OPEN_SHIFT_CONFLICT`.
- **`close_shift` بيقفل صف الوردية** (`lock_shift_for_update`, blocking FOR
  UPDATE) قبل أي فحص/كتابة — الإغلاق التاني يشوف `closed` تحت القفل ويترفض.
- **صيغة الكاش المتوقع الكاملة** (`_cash_movement_expected_effect`):
  `opening_float + active cash payments + cash_in − cash_out − petty_cash −
  safe_drop ± correction`. `drawer_open` أثره صفر.
- **correction لازم يحمل اتجاه صريح** (`increase|decrease`، عمود
  `cash_movements.direction` جديد) — مرفوض لغير correction، وإجباري لها.
  correction قديمة بلا اتجاه **تُستبعد** من الحساب وتظهر في تحذير
  reconciliation (`cash_movements_warning`) بدل تخمين اتجاهها.
- **branch isolation** عبر `core.services.assert_branch_access` (super_admin
  بس بيتخطى) على: open / current / list / handover / report / close /
  cash-movements / invoices. وردية غير موجودة بقت 404 (كانت 400 في بعضها).

---

## Gate 4C — Order state, ownership, reversals, concurrency

### Root causes
- الانتقالات نص حر بلا state machine.
- إنشاء Order مايقفلش الطاولة ومافيش invariant يمنع طلبين نشطين لنفس الطاولة.
- `DiningOrder` يحفظ `waiter_id` فقط — لا creator ولا item actor.
- `refund_order_item` مايقفلش الطلب، وبلا Payment reversal يرجع للأصل.

### التصميم كما نُفِّذ
- **state machine مركزية** `ORDER_TRANSITIONS` + `assert_order_transition` —
  الرحلة held→open→in_kitchen→served→paid→refunded؛ cancelled نهائية؛ الرجوع/
  القفز غير المنطقي مرفوض؛ الانتقال لنفس الحالة idempotent.
- **one-active-order:** partial unique index `uq_active_order_per_table` (على
  held|open|in_kitchen|served) + قفل الطاولة (`lock_table_for_update`، blocking)
  + فحص `get_active_order_for_table` في `create_order`، مع `IntegrityError`
  backstop برسالة واضحة.
- **actor attribution:** `dining_orders.created_by` (المنشئ، ثابت، منفصل عن
  `waiter_id` القابل للنقل) و`dining_order_items.added_by` (مين أضاف الصنف).
- **refund بيقفل صف الطلب** (`get_order_for_update` NOWAIT) ويعيد فحص حالة
  الصنف تحت القفل — مرتجعان متزامنان: واحد بس ينجح.
- **refund reversal Payment:** لطلب مباشر، عكس Payment صريح (سالب) مرتبط بالـ
  tender الأصلي (`original_payment_id`, `source='dining_refund'`) منسوب لوردية
  المسترجِع — عشان تقرير الوردية يخصم المرتجع من الكاش/البطاقة صح. بيتوزّع
  بالتناسب على الـ tenders الأصلية.
- **السجل المالي المكتمل لا يتغير مبلغه** — العكس بصف reversal صريح (قيد +
  Payment سالب)، والـ totals الأصلية للطلب تفضل كسجل تاريخي.

### حالة تاريخية أُغلقت في M5a
- **step-up مالي دقيق لـ `payment_void`/`dining_refund`** كان مؤجَّلًا في
  أول حزمة، ثم نُفِّذ بالكامل في M5a كما هو موثّق لاحقًا: recent-auth proof
  مربوط بالعملية والكيان، تحقق backend، وتدفق refund في الواجهة.
- **split refund allocation صريح**: المرتجع الحالي بيوزّع بالتناسب على الـ
  tenders الأصلية تلقائيًا بصورة حتمية وآمنة. اختيار توزيع يدوي من المستخدم
  يظل تحسين منتج اختياريًا، وليس فجوة سلامة أو شرط Gate 4.

---

## Migration

`c9f1a4d7e2b8_gate_4_dining_settlement_shift_order_integrity.py` (إضافية،
`down_revision = b8f4d2a19c07`):
- جدول `dining_settlements` + فهارسه (منها الـ idem key الجزئي).
- `payments.source`, `payments.original_payment_id` (+ فهارس).
- `dining_orders.created_by`, `dining_order_items.added_by`.
- `cash_movements.direction`.
- partial unique indexes: `uq_active_order_per_table`,
  `uq_open_shift_per_branch_cashier` (Postgres وSQLite، بـ where clause — فهرس
  unique غير جزئي كان هيمنع الطاولة/الكاشير من صف تاني تاريخي).

**rollback honesty:** downgrade بيشيل الجدول/الأعمدة/الفهارس. بعد ما التطبيق
يبدأ يسجّل settlements/idempotency، الـ downgrade بيفقد ledger الـ exactly-once
ونسب الـ actor، وبيعيد فتح سباقات الفتح المزدوج — **maintenance-only، مش rollback
إنتاجي آمن** بعد وجود تسويات حقيقية. مافيش بيانات سابقة للـ migration بتتدمر
بالـ upgrade.

---

## أوامر التحقق ونتائج الحزمة الأصلية (سجل تاريخي)

**Backend full suite** (`.venv/bin/pytest tests/`، SQLite):
**1992 passed · 24 skipped · 0 failed** (282s). (الأرقام دي منفصلة عمدًا،
مش إجمالي JUnit واحد.)

**Real-Postgres concurrency** (قاعدة throwaway، admin DSN):
- `tests/test_gate4_concurrency.py`: **4 passed** — open-shift double-open،
  idempotent double-submit، one-active-order-per-table، concurrent-refund.
- `tests/test_dining_paid_concurrency.py` (regression): **5 passed**.

**Migration cycle** (قاعدة معزولة أنشأتها وحذفتها بنفسي، **مش** قاعدة التطوير
المشتركة): `upgrade head → downgrade b8f4d2a19c07 → upgrade head` — نجح
الاتجاهين بلا أخطاء. `alembic heads`: رأس واحد `c9f1a4d7e2b8`.

**Frontend:**
- `pnpm --filter el-kheima validate:i18n`: أخضر (3115 مفتاح parity، صفر فراغ).
- `pnpm --filter el-kheima type-check`: نظيف.
- `pnpm --filter el-kheima test:frontend`: **60 passed** (7 ملفات).
- `pnpm --filter el-kheima build`: نجح.
- `pnpm --filter public type-check` / `build`: نجحا (تحذير bundle size قديم غير
  مانع).

**أخرى:** `git diff --check` نظيف؛ `docker compose config` (base + prod) نجحا؛
`scripts/gate4_reconciliation.py` شغّال (قراءة فقط).

`ruff`/`mypy`/pyright مش gates مهيّأة في الريبو (AGENTS.md §7) فلم تُدَّعَ. تحذيرات
pyright على constructors الـ SQLAlchemy في factories الاختبارات
(`make_outlet`/`make_item`) سابقة لـ Gate 4 (الـ gate ماضفش أي عمود إجباري
جديد)، مش انحدار من الحزمة دي.

---

## الملفات المتغيّرة/الجديدة

**Backend (منطق):** `app/core/config.py`، `app/modules/dining/{models,crud,
services,api/router}.py`، `app/modules/dining/payment_policy.py` (جديد)،
`app/modules/finance/{models,crud,services,schemas,api/router}.py`.
**Migration:** `alembic/versions/c9f1a4d7e2b8_*.py` (جديد).
**Script:** `scripts/gate4_reconciliation.py` (جديد، قراءة فقط).
**Tests:** `tests/test_gate4_concurrency.py` (جديد)، `tests/conftest.py`،
`tests/test_api/{test_dining_http,test_dining_paid_atomicity,test_finance,
test_finance_http,test_food_cost_report,test_pos_full_cycle_http,
test_refund_after_payment_http}.py`.
**Frontend:** `apps/el-kheima/src/components/DiningOrderDetailModal.vue`
(idempotency key generation + عرض حالات الخطأ الجديدة).

**تنظيف عرضي مرتبط:** أُزيل تعريف مكرر لـ `dining/crud.py::list_tables_with_orders`
(الثاني كان بيحجب الأول بصمت؛ الاتنين متطابقين).

---

## Root bugs حقيقية اتكشفت وأُصلحت أثناء العمل

1. **تعريف مكرر لـ `list_tables_with_orders`** في `dining/crud.py` (النسخة
   التانية بتحجب الأولى) — أُزيلت الأولى، فُضِّل تعريف واحد.
2. **SQLite fallback للفهارس الجزئية** كان unique غير جزئي — كان هيمنع أي
   طاولة/كاشير من صف تاني تاريخي؛ صُحِّح لـ partial index حقيقي على الاتنين.
3. **split كان يكرر حصة الغرفة محاسبيًا** (قيد إيراد كامل + شحنة فوليو) — الآن
   الإيراد المرحَّل = order.total بالظبط، بلا double counting.

## حالة البنود التي كانت متبقية
- step-up المالي أُغلق في M5a.
- توزيع split refund التلقائي آمن؛ التوزيع اليدوي وmulti-folio امتداد منتج
  لاحق بعقد مستقل، وليس blocker لـGate 4.
- ترجمة POS/KDS أُنجزت ضمن Gate 5، وكانت أصلًا خارج نطاق Gate 4.

المراجعة المستقلة النهائية اكتملت في 22 يوليو وأصلحت الملاحظات المحدودة
المذكورة في أول التقرير. لم يحدث commit أو push أو نشر من worktree المراجعة.

---

## جولة مراجعة Codex المستقلة الأولى — التصحيحات (2026-07-20)

مراجعة Codex مستقلة على فرع `gate-4-dining-payment-shift-order-integrity`
أثبتت 10 ملاحظات حقيقية (5 High + 5 Medium). كلها اتصلحت بإعادة استخدام
أنماط الكود الموجودة (NOWAIT+409، `assert_branch_access`، `resolve_pin_approval`،
`lock_shift_for_update`) — بدون أي آلية موازية. **لا commit ولا push**؛ بانتظار
جولة مراجعة نهائية.

### High 1 — الدفع/حركة الكاش ما كانوش بيتسلسلوا مع إغلاق الوردية (regression) ✅
- **الجذر:** `settle_order` كان بيقرا الوردية عبر `get_open_shift` (قراءة غير
  مقفولة)، و`record_cash_movement` عبر `get_shift` (نفس الشيء) — فدفعة كانت
  تُنسب لوردية بتتقفل في نفس اللحظة وexpected_cash محسوب من غيرها.
- **الإصلاح:** `finance.crud.lock_open_shift_for_update` جديدة (SELECT FOR
  UPDATE **NOWAIT** على الوردية المفتوحة لـ(فرع، كاشير)، `populate_existing`)
  + `finance.services._lock_open_shift_or_conflict` بتترجم فشل القفل لـ
  `ShiftCloseInProgressError` (409 `SHIFT_CLOSE_IN_PROGRESS`). `settle_order`
  و`_post_refund_reversals` بيستخدموها؛ `record_cash_movement` بقى يستخدم
  `lock_shift_for_update` (blocking، shift_id معروف). ترتيب قفل موثّق: **Order
  قبل Shift** (settle بيقفل الطلب أولًا ثم الوردية) — مفيش مسار بياخد Shift
  قبل Order فمفيش deadlock. `add_payment` (تسوية فوليو) اتحوّلت لنفس الـ helper.
- **إثبات (Postgres حقيقي، `test_gate4_concurrency.py`):**
  `TestPaymentVsCloseShift` (الدفع بيترفض 409 وهو ماسك قفل الإغلاق، ثم ينجح بعد
  التحرير على وردية مفتوحة)، `TestCashMovementVsCloseShift` (الحركة بتترفض
  'الوردية مقفولة' ومفيش صف حركة بيتكتب).

### High 2 — باقي mutations الطلب ما كانتش بتقفل الطلب (defect سابق) ✅
- **الجذر:** بس `settle_order`/`refund_order_item` كانوا بيقفلوا الطلب. `update_
  order_status`/`add_items_to_order`/`void_order_item`/`transfer_order_table`/
  `merge_orders`/`apply_order_discount` كانوا بيقروا غير مقفول — فدفع + إلغاء
  متزامنين سابوا طلب paid متعلّم cancelled (مُثبَت حيًا).
- **الإصلاح:** helper موحّد `_lock_order_or_conflict` (نفس `get_order_for_update`
  NOWAIT + `OrderPaymentConcurrencyError`→409) بيتنادى من كل mutation، وإعادة
  فحص الحالة تحت القفل. `transfer_order_table` بيقفل الطاولة الوجهة كمان
  (+IntegrityError backstop على `uq_active_order_per_table`). `merge_orders`
  بيقفل الطلبين بترتيب id تصاعدي حتمي (منع deadlock مع دمج عكسي). كل الراوترات
  بتترجم `OrderPaymentConcurrencyError`→409.
- **إثبات:** `TestPaidOrderMutationLockContention` (6 mutations: كل واحدة بتاخد
  409 وهي والطلب مقفول)، `TestPaidVsCancelRace` (سباق دفع/إلغاء: مستحيل الطلب
  يخلص cancelled ومعاه settlement/Payment موجب).

### High 3 — split refund بكاش+غرفة ما كانش بيعكس حصة الكاش (regression) ✅
- **الجذر:** `refund_order_item` كان بيفرّع على `if order.folio_id:` boolean —
  والـ folio_id بيتحط لو *أي* جزء اتحمّل على الغرفة، فطلب split (كاش+غرفة) كان
  بياخد مسار عكس الفوليو بس ويسيب حصة الكاش من غير عكس خالص.
- **الإصلاح:** `_post_refund_reversals` جديدة بتقود العكس بالـ tenders الأصلية
  الفعلية (صفوف Payment المباشرة + حصة الغرفة = order.total − مجموع المباشر)،
  وتوزّع المرتجع بالتناسب على *كل* tender: كل مباشر → Payment سالب بحصته، وحصة
  الغرفة → خفض شحنة الفوليو.
- **إثبات:** `test_split_cash_room_refund_reverses_both_portions_proportionally`
  (كاش 63 + غرفة 63 → مرتجع كامل بيعمل Payment كاش −63 **و** خفض شحنة الفوليو 63).

### High 4 — مسار المرتجع fail-open وبيرحّل على حساب غلط (defect سابق) ✅
- **الإصلاح (a):** `_reduce_folio_charge_for_refund` بقى **fail-closed** — الفوليو
  المقفول/المفقود أو الشحنة الغائبة بترفع `ValueError` بدل بلع الفشل بعد logging،
  و`refund_order_item` بيعمل rollback كامل. كل قيود المرتجع بقت `strict=True`.
- **الإصلاح (b):** العكس المباشر بيرحّل على *حساب الطريقة الأصلي نفسه* عبر
  `payment_policy.resolve_direct_tender_account(method)` (cash→1100، card/wallet→
  حساب المقاصّة المهيّأ)، مش 1100 ثابت.
- **إثبات:** `test_card_tender_refund_posts_against_card_clearing_account_not_cash`
  (العكس بيتقيّد على 1120 مش 1100)، `test_refund_fails_closed_when_folio_closed_
  and_rolls_back_entirely` (فوليو مقفول → 400 + rollback كامل، مفيش صفوف عكس يتيمة).

### High 5 — عزل الفرع ناقص على endpoints دايننج/مالية (defect سابق) ✅
- **الإصلاح:** `assert_branch_access` (المُعاد استخدامه) اتطبّق على: دايننج
  refund/void/transfer/add-items/discount/merge/waiter عبر helper
  `_assert_order_branch`، وعلى finance `report/pdf` و`cash-movements` list
  (كانوا بيفحصوا الملكية بس، فمدير فرع تاني كان بيعدّي). مراجعة كل endpoints
  الجولة اتعملت.
- **إثبات (HTTP):** `test_refund_cross_branch_manager_rejected`،
  `test_cross_branch_manager_cannot_view_shift_report_or_pdf`،
  `test_cross_branch_manager_cannot_list_cash_movements` (كلها 403 cross-branch،
  والنفس-فرع 200 مغطّى في التستات الموجودة). تستات الصلاحيات/الدايننج المتأثرة
  اتحدّثت لتستخدم مستخدمين Employee-linked (نفس نمط Gate 1B).

### M1 — عقد idempotency ✅
- tolerance الـ allocation بقى مقارنة Decimal دقيقة بعد `.quantize()` للطرفين
  (مش ±0.01 اللي كان بيسمح بانحراف قرش). **قرار الـ header (موثّق):** فضل
  اختياري (backward-compatible) — الـ exactly-once مضمون بـ `UNIQUE(order_id)` +
  فحص الحالة تحت القفل (retry بلا key بياخد 409 `ORDER_ALREADY_PAID` نظيف، مش
  دفع مكرر).

### M2 — تقرير الوردية + لقطة التسوية ✅
- **تقرير الوردية:** المرتجعات/العكوس (Payment سالب) بقت بند صريح منفصل
  (`refunds_total`/`refunds_count`) بدل خصم صامت؛ الإجماليات بقت gross؛ الكاش
  المتوقع بيحسب الصافي داخليًا (نفس السلوك رقميًا). حصة الغرفة بقت بند
  (`total_room`) بتتجمّع من لقطة `tender_breakdown` (كانت غايبة تمامًا).
- **لقطة التسوية:** عمود `dining_settlements.tender_breakdown` JSON (migration
  `d2b4a1c3f7e9`، إضافي) بيلقط توزيع الـ tenders وقت التسوية — مصدر تاريخي مستقل
  عن حالة Payment.
- **إثبات:** `test_shift_report_shows_refunds_as_explicit_separate_line`،
  `test_shift_report_includes_room_tenders_from_settlement_snapshot`.

### M3 — قفل المدير لوردية غيره بلا موافقة/سبب/تدقيق ✅
- `close_shift`: لما `closed_by != shift.cashier_id` بقى يتطلب سبب صريح (notes)
  + `resolve_pin_approval` (بيوصّل حقول approver_* الـ stale) + `AuditLog`
  (`close_other_shift`). `force_close` فضل حقل متوافق-خلفيًا بلا أثر بوّابي (آلية
  رفض الفرق أُلغيت بقرار Mohamed).
- **إثبات:** `test_manager_can_force_close_other_cashiers_shift` (محدّث: سبب +
  AuditLog)، `test_manager_close_other_shift_without_reason_rejected` (400).

### M4 — تناقض invariant الحالة ✅
- `get_active_order_for_table` بقى يستخدم `ACTIVE_TABLE_ORDER_STATUSES`
  (held|open|in_kitchen|served) المطابقة للـ partial index بالظبط (refunded
  اتشال)، والطلب المُرتجَع بالكامل بقى يحرّر الطاولة. تحويل in_kitchen→in_kitchen
  بقى no-op حقيقي (مفيش تذاكر مطبخ مكررة).

### M5 — step-up مالي + endpoint نقل النادل ✅ (الاتنين نُفِّذا بالكامل)
- **(b) نُفِّذ ✅:** `PATCH /dining/orders/{id}/waiter` (مدير+، سبب إجباري،
  AuditLog `transfer_waiter`، بيسيب `created_by` الأصلي). إثبات:
  `TestDiningWaiterTransferHTTP` (إعادة إسناد + تدقيق + حفظ المنشئ + رفض بلا سبب
  + رفض نادل عادي).
- **(a) نُفِّذ ✅ (2026-07-20، بعد ما Codex بقى غير متاح — نفّذته أنا مباشرة من
  غير وكيل):** توسيع step-up المالي لـ`payment_void`/`dining_refund` بنطاق
  exact-intent. راجع القسم الجديد تحت "جولة M5a — step-up المالي" للتفاصيل
  الكاملة. **مفيش بند مؤجَّل متبقٍّ في Gate 4.**

### الملفات المتغيّرة/الجديدة (هذه الجولة)
- **Backend:** `dining/{services,crud,models,schemas,api/router}.py`،
  `finance/{services,crud,schemas,api/router}.py`.
- **Migration جديدة:** `alembic/versions/d2b4a1c3f7e9_*.py` (tender_breakdown، إضافية).
- **Tests:** `tests/test_gate4_concurrency.py` (High 1/2 proofs)،
  `tests/test_api/{test_refund_after_payment_http,test_finance,test_finance_http,
  test_dining_http,test_permissions}.py`.

### التحقق (هذه الجولة)
- migration cycle على قاعدة معزولة أنشأتها/حذفتها بنفسي: upgrade head →
  downgrade c9f1a4d7e2b8 → downgrade b8f4d2a19c07 → upgrade head، رأس واحد
  `d2b4a1c3f7e9`، العمود موجود بعد إعادة الـ upgrade. **لم تُلمس قاعدة التطوير المشتركة.**
- `git diff --check` نظيف.

---

## جولة M5a — step-up المالي لـpayment_void/dining_refund (2026-07-20)

Codex مش متاح للمراجعة حاليًا (قرار محمد صريح: "اعمل انت الازم... بدون وكلاء").
البند الوحيد المتبقي من جولة المراجعة الأولى (M5a) نُفِّذ مباشرة، من غير أي
وكيل فرعي — أنا اللي قريت الكود، كتبت التعديل، وراجعته بنفسي.

### التصميم
- **"payment_void"** = `finance.services.void_payment` (عكس Payment مسجّل
  فعليًا في الدفاتر — عبر `POST /finance/payments/{id}/void`)، **"dining_refund"**
  = `dining.services.refund_order_item` (مرتجع صنف بعد الدفع). الاتنين دول —
  مش `void_order_item` قبل الدفع (لسه محمي بـPIN موافقة مدير بس، عمدًا — برد
  المذكور صراحةً في الـbrief §2.4: "لا لكل ضغطة POS").
- **إعادة استخدام كاملة لآلية Gate 2B3A/2B3B** — مفيش نظام proof موازٍ:
  - `app/core/kernel/auth/step_up.py`: `payment_void_scope(payment_id, reason)`
    و`dining_refund_scope(order_id, item_id, reason)` — نفس نمط باقي الـscope
    builders (SHA-256 لمستند JSON حتمي، `reason` بيتهاش قبل ما يدخل الـscope).
  - `app/core/kernel/auth/router.py`: `_STEP_UP_PURPOSES` بقت تشمل
    `payment_void`/`dining_refund`، عقود typed جديدة (`_PaymentVoidIntent`،
    `_DiningRefundIntent`، الاتنين `extra="forbid"` + `reason` إجباري ≥3 حروف)،
    و`issue_step_up` بقى يحسب الـscope الصح لكل واحدة منهم.
  - **تنظيف تكرار حقيقي أثناء العمل:** `_consume_step_up_or_raise` كانت دالة
    خاصة جوه `core/api/router.py` بس — بما إن finance وdining بقى عندهم نفس
    الحاجة، اتنقلت لموديول مشترك جديد `app/modules/core/api/step_up_utils.py`
    (لسه في الـAPI layer عمدًا، مش `core.services`، لأنها بترفع `HTTPException`
    مباشرة — راجع CLAUDE.md §4). `core/api/router.py` بقى بيستوردها بدل ما
    يعرّفها لوحده — refactor سلوكه واحد 100%، الأربعة endpoints القديمة
    (`user_role_update`/`permission_override_upsert`/`permission_override_revoke`/
    `setting_upsert`) اتأكد إنهم لسه عادّين صح من غير أي تعديل في تستاتهم.
  - `finance/api/router.py`'s `void_payment` وdining/api/router.py`'s
    `refund_order_item`: كل واحد بيحسب الـscope من الـpayload الفعلي بتاعه (نفس
    نمط الأربعة endpoints القديمة)، يستهلك `X-Step-Up-Token`، وبعدين بس ينادي
    الـservice. لا تعديل على الـservices نفسها خالص (step-up قرار HTTP-layer
    بحت، مش business logic).
- **Frontend:** `StepUpConfirmModal.vue`'s `purpose` union اتوسّع
  (`payment_void`/`dining_refund`). `DiningOrderDetailModal.vue`'s تدفق
  المرتجع اتبنى من جديد — كان بيعرض `AppTextarea` inline للسبب وينادي الـAPI
  مباشرة (زي `void_order_item` بالظبط)، بقى بيفتح `StepUpConfirmModal` (نفس
  المكوّن اللي `SessionsView.vue`/`SettingsView.vue`/`PermissionsView.vue`
  بيستخدموه) اللي بياخد كلمة السر + السبب في خطوة واحدة، وبيبعت الـtoken في
  `X-Step-Up-Token` header. **`void_payment` (finance) مفهوش أي شاشة frontend
  بتناديه أصلاً حتى دلوقتي** (اتأكد بالبحث في الكود) — الحماية بقت backend-only،
  مفيش UI يتيم يحتاج تعديل.

### إثبات (اختبارات جديدة، مش بس تحديث الموجود)
- `test_refund_without_step_up_token_rejected` (428 `STEP_UP_REQUIRED`)،
  `test_refund_with_step_up_token_for_different_item_rejected` (403
  `STEP_UP_INVALID` — proof مربوط بـitem_id بالظبط، مش قابل لإعادة الاستخدام
  لصنف تاني).
- `test_void_payment_without_step_up_token_rejected` (428)،
  `test_void_payment_with_step_up_token_for_different_payment_rejected` (403 —
  proof مربوط بـpayment_id بالظبط).
- كل استدعاءات refund/void HTTP الناجحة الموجودة (9 مواقع في
  `test_refund_after_payment_http.py`، 5 مواقع في `test_finance_http.py`) بقت
  بتصدر step-up token حقيقي عبر helper مشترك (`_refund_headers`/
  `_void_payment_headers`) قبل النداء — التستات اللي بتفشل بـ403/422 قبل ما
  توصل لجسم الـendpoint (صلاحية أقل من مدير، سبب قصير) اتسابت زي ما هي عمدًا،
  مالهاش لازمة لـstep-up.

### التحقق (هذه الجولة)
- **Backend suite كامل:** **2008 passed · 33 skipped · 0 failed** (305 ثانية).
- **الملفات الثلاثة المتغيّرة مباشرة:** `test_refund_after_payment_http.py` +
  `test_finance_http.py` + `test_step_up_control_plane.py` (تأكيد الـrefactor
  ماكسرش الأربعة endpoints القديمة) = **147 passed** لوحدهم.
- **Concurrency حقيقي على Postgres** (قاعدة throwaway): 18/18 (لسه سليمة —
  التغيير ده HTTP-layer بحت، مالوش أثر على منطق القفل).
- **مفيش migration جديدة** (step-up proof بيتخزن في الجدول الموجود من Gate
  2B3A، مفيش عمود جديد) — `alembic heads` لسه رأس واحد `d2b4a1c3f7e9`.
- **Frontend:** `validate:i18n` نظيف (3115 مفتاح)، `type-check:all` نظيف
  (el-kheima + public)، `test:frontend` **60 passed**، `build:all` نظيف.
- `git diff --check` نظيف؛ `git log`: **صفر commit، صفر push**.

**النتيجة: Gate 4 بقى مُنفَّذة بالكامل — الثلاث شرائح + كل ملاحظات Codex (High
1-5 وMedium 1-4) + M5a step-up المالي. مفيش blocker برمجي متبقٍّ داخل
Gate 4.** المراجعة المستقلة النهائية تمت في 22 يوليو؛ اعتماد Mohamed وقيود
البيئة الميدانية المذكورة أعلاه يظلان قبل Gate 9.
