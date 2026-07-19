# Gate 4 — Dining Payment, Shift & Order Integrity

**الحالة:** عقد تنفيذ جاهز لكلودي بعد اعتماد Gate 3، على الفرع النظيف
`gate-4-dining-payment-shift-order-integrity`. يُنفَّذ بلا commit أو push، ثم
يتوقف لمراجعة Codex النهائية.

**الهدف:** تحويل رحلة Dining الحالية من «الطلب يمكن أن يصبح paid» إلى عقد
تشغيلي ومالي يمكن إثباته: كل تحصيل يظهر مرة واحدة فقط، منسوبًا للكاشير
والوردية وطريقة الدفع والطلب، والـsplit/refund/void لا تترك أثرًا جزئيًا أو
مكررًا، ولا يمكن فتح طلبين لنفس الطاولة بسبب سباق.

هذا Gate كبير متعمدًا، لكنه ليس إعادة كتابة. يُنفذ في ثلاث شرائح داخل نفس
الحزمة، وتُغلق كل شريحة باختباراتها قبل التالية.

---

## 0. القرارات الثابتة

- اسم المنتج **El Kheima Beach Resort OS**.
- Restaurant وCafé مجال واحد اسمه **Dining**؛ لا إعادة إنشاء الموديولين.
- الـBackend الحالي هو مصدر الحقيقة، ولا نقل من Trucker/Click أو أي مشروع
  قديم. القديم مرجع رحلة تشغيل فقط.
- وضع QR المستقبلي `view_and_call`، والـQR ما زال تجريبيًا وغير مطبوع؛ لا
  Public/QR/Guest Service في هذا Gate.
- لا `float` للمال، ولا تعديل صامت لسجل مالي مكتمل، ولا `except: pass` حول
  أثر مالي.
- قواعد Gate 2 للصلاحيات وPIN/step-up والتدقيق تُعاد استخدامها؛ لا نظام
  موافقات موازٍ.
- قرار Mohamed الحالي في فروق الوردية محفوظ: الوردية يمكن أن تُغلق مع الفرق،
  لكن الفرق يُسجل ويظهر للمحاسب بوضوح. لا تعاد آلية رفض الفرق القديمة من غير
  قرار جديد.
- لا تُخمن بيانات إنتاج قديمة، ولا actor/shift/payment غير معروف. أي backfill
  غير قابل للإثبات يتحول لتقرير reconciliation، لا لبيانات مصطنعة.

---

## 1. خط الأساس المؤكد من الكود

يجب على Claude إعادة التحقق من هذه النقاط قبل التعديل، لكنها مؤكدة عند فتح
الحزمة:

1. `_mark_order_paid()` أصبح atomic في Gate 1B بالنسبة إلى حالة الطلب،
   FolioCharge، المخزون، قيد الإيراد، والزيارة؛ ويقفل Order/Folio/Product.
2. رغم ذلك، دفع Dining المباشر **لا ينشئ `finance.Payment`**، ولا يعرف
   `cashier_id` أو `shift_id`. تقرير الوردية يقرأ `Payment.shift_id`، ولذلك
   بيع Dining قد يغيب تمامًا عنه.
3. `payment_method` موجود كنص واحد على `DiningOrder`؛ لا يمثل split tenders،
   ولا توجد idempotency key لطلب الدفع نفسه.
4. `split_bill()` مسار موازٍ للدفع: لا يستخدم وحدة العمل الصارمة كاملة، لا
   يقفل الطلب، يستدعي خصم مخزون/ترحيلًا قد يعملان بـnested commits، ولا ينشئ
   Payment rows. وهو يتسابق مع paid/add/void/discount.
5. `refund_order_item()` لا يقفل Order/Item/FolioCharge، ويبتلع فشل خفض شحنة
   الفوليو بعد logging؛ لا يوجد Refund/Payment reversal يرجع إلى التحصيل
   الأصلي.
6. `Payment.reference` بلا unique/idempotency constraint، و`Payment` لا يحمل
   مصدرًا عامًا واضحًا أو original payment/reversal relation.
7. `open_shift()` يستخدم check-then-insert بلا DB invariant أو lock؛ طلبان
   متزامنان قد يفتحان ورديتين لنفس الكاشير والفرع.
8. `close_shift()` لا يقفل صف الوردية؛ إغلاقان متزامنان قد يكتبان count lines
   أو قيم reconciliation مرتين.
9. حساب `expected_cash` الحالي هو `opening_float + cash payments` فقط؛ لا
   يدخل CashMovement. الأنواع الحالية هي cash_in/cash_out/petty_cash/
   safe_drop/drawer_open/correction.
10. Finance shift endpoints تقبل `branch_id` من العميل، وبعضها لا يثبت ملكية
    فرع المستخدم عبر `assert_branch_access`.
11. `CashierShiftClose` و`ShiftPanel.vue` ما زالا يحملان تعليقات وحقول
    force-close/PIN قديمة رغم أن الـservice يغلق الوردية دائمًا ويسجل الفرق.
12. `DiningOrder` يحفظ `waiter_id` فقط؛ لا يحفظ creator، ولا actor إضافة
    الصنف، والدفع لا يحفظ cashier/shift.
13. إنشاء Order جديد لا يقفل VenueTable ولا توجد partial unique index تمنع
    طلبين نشطين لنفس الطاولة. الانتقالات العامة للحالة ليست state machine.
14. API methods الحالية (`cash|card|room|wallet`) لا تطابق Finance methods
    بالكامل، وقيد البيع المباشر يستخدم Cash `1100` حتى لو النص يقول card أو
    wallet. لا يجوز إصلاح mapping المالي بالتخمين.

مراجع إلزامية قبل التعديل:

- `docs/audits/gate-1b-financial-atomicity-plan.md`
- `docs/audits/SMART_EXECUTION_ROADMAP.md`
- `docs/decisions/0003-super-admin-control-plane.md`
- `docs/FRONTEND_TESTING.md`
- أقسام Trucker/Dining في `wagdy.md`
- `backend/app/modules/dining/{models,schemas,crud,services}.py`
- `backend/app/modules/dining/api/router.py`
- `backend/app/modules/finance/{models,schemas,crud,services}.py`
- `backend/app/modules/finance/api/router.py`
- اختبارات Dining paid/refund/finance/shift/concurrency الحالية

---

## 2. ثوابت القبول المالية والتشغيلية

### 2.1 Settlement وPayment

- كل عملية دفع ناجحة لها settlement واحد غير قابل للتكرار مرتبط بالطلب.
- كل tender مباشر محصل (cash/card/وسيلة مهيأة) له `Payment` واحد بالضبط،
  مرتبط بالطلب والكاشير والوردية والطريقة والمبلغ ووقت التحصيل.
- room charge يمثل ذمة/FolioCharge، وليس cash داخل الدرج ولا دفعة checkout
  ثانية. يجب أن يظل قابلًا لإعادة إنتاج split receipt من سجل تفصيلي، من غير
  double counting عند تسوية الفوليو لاحقًا.
- مجموع tender allocations يساوي `order.total` بدقة Decimal وفق قاعدة rounding
  واحدة. لا tolerance غامضة تسمح بزيادة/نقص فعلي.
- الدفع المباشر لا ينجح بلا وردية مفتوحة لنفس الكاشير والفرع. room charge لا
  يزيد cash expected، لكنه يظل منسوبًا للـactor.
- طريقة الدفع تُحل من سياسة/سجل typed خاص بالفرع أو بنية موجودة مكافئة إن
  وُجدت. Cash يمكن ربطه بالحساب الموجود `1100`، وroom بالذمم `1150`؛ card/
  wallet لا تُربط بحساب من اختراع الوكيل. لو لم توجد mapping موثوقة، تفشل
  الطريقة fail-closed برسالة configuration واضحة حتى تُهيأ.
- أي card/wallet external reference requirement يكون explicit في تعريف
  الطريقة، لا شرطًا متناثرًا داخل UI.

### 2.2 Idempotency

- paid وsplit يقبلان `Idempotency-Key` ثابتة يولدها العميل مرة لكل محاولة
  منطقية ويعيد استخدامها عند network retry.
- نفس key + نفس order + نفس canonical intent يعيد نفس النتيجة بلا أثر جديد.
- نفس key مع intent مختلف يرفض 409.
- key مختلفة على Order مدفوع ترفض `ORDER_ALREADY_PAID`.
- حمايات idempotency في DB، لا memory/Redis فقط، وتنجح تحت PostgreSQL حقيقي.

### 2.3 Transaction boundary

عملية settlement الواحدة تشمل في commit واحد:

1. lock وإعادة فحص Order وحالته؛
2. lock وإعادة فحص الوردية عند وجود tender مباشر؛
3. settlement/tender records؛
4. FolioCharge للجزء المحمل على الغرفة؛
5. inventory/COGS؛
6. journal lines الصحيحة حسب كل allocation؛
7. customer visit؛
8. حالة الطلب والطاولة؛
9. audit/actor attribution.

أي فشل في أي بند يعمل rollback كامل. لا nested commit، ولا notification قبل
نجاح commit. البث realtime بعد النجاح فقط.

### 2.4 Refund / void / discount

- Refund لا يتجاوز المتبقي القابل للرد ولا يتكرر تحت retry/concurrency.
- Refund مباشر يرجع إلى Payment أصلي؛ room-charge refund يرجع إلى الشحنة
  الأصلية. split refund لا يخمن طريقة العكس: الطلب يحدد allocation آمنًا أو
  يطلب توزيعًا صريحًا مجموعُه يساوي refund المحسوب.
- السجل المالي المكتمل لا يتغير في مبلغه؛ العكس يتم بسجل reversal صريح، مع
  الحفاظ على حقول compatibility الحالية إن لزم.
- refund/void يحمل actor وreason وapprover ووقت ومرجع الأصل، ويستخدم permission
  الحالية. وسّع step-up الموجود للأفعال المالية الأعلى خطورة فقط
  (`payment_void` و`dining_refund`) بنطاق exact intent، لا لكل ضغطة POS.
- void item قبل الدفع وdiscount يظلان على policy/PIN الحالية، لكن كل mutation
  يقفل Order نفسه حتى لا يتسابق مع الدفع، ويكتب reason/approver بوضوح. أضف
  reason حقيقي للخصم إن لم يكن موجودًا؛ لا audit لعملية حساسة بلا سبب.

### 2.5 Shift وcash reconciliation

- DB يمنع أكثر من Shift مفتوحة لنفس `(branch_id, cashier_id)`، مع error 409
  مفهوم تحت السباق.
- فتح/عرض/إغلاق/report/handover يطبق branch isolation من السيرفر.
- cash expected يحسب بالصيغة الموثقة:

  `opening float + active cash payments + cash_in - cash_out - petty_cash - safe_drop ± explicit correction`

  `drawer_open` أثره صفر. correction الجديدة يجب أن تحمل اتجاهًا صريحًا؛ لا
  تخمن اتجاه السجلات التاريخية. legacy corrections تظهر في warning/report
  reconciliation حتى تُراجع.
- إغلاق Shift يقفل الصف، يمنع إغلاقًا ثانيًا، ويثبت هل payment المتزامنة دخلت
  قبل الإغلاق أو رُفضت بعده؛ لا حالة رمادية.
- مدير يغلق وردية شخص آخر يحتاج permission/step-up أو approval المعتمد وسببًا
  صريحًا، ويترك AuditLog. الكاشير لا يغلق وردية غيره.
- نظف عقد force-close القديم في backend/frontend بطريقة backward-compatible
  موثقة، لأن قرار المنتج الحالي هو الإغلاق مع تسجيل الفرق لا رفضه.
- report يبين tenders، room charges منفصلة، refunds/reversals، voids، manual
  cash movements، expected/count/variance، وأي legacy unreconciled warning.

### 2.6 Order state, ownership, and one active order

- عرّف state machine واحدة للخادم؛ الانتقالات لا تُترك لregex وحده.
- كل mutation مالية أو سعرية تقفل Order وتعيد فحص state تحت القفل.
- احتفظ بـ`waiter_id` للتوافق باعتباره assigned waiter، وأضف/استخرج بصورة
  موثوقة: creator، item added_by، cashier/payment actor، approver، ونقل waiter.
- تغيير assigned waiter يحتاج endpoint/permission/reason/AuditLog ولا يمسح
  التاريخ.
- لطاولات Dining الحالية فقط (لا تبنِ Service Location أو QR): DB partial
  unique invariant + table lock يمنع أكثر من Order في حالات
  `held|open|in_kitchen|served` لنفس `table_id`.
- قبل migration شغّل تقرير duplicates قراءة فقط. إذا توجد بيانات حقيقية
  متعارضة، لا تغلق أو تدمج أو تحذف تلقائيًا؛ توقف بتقرير IDs وتأثير وخيارات
  reconciliation.
- transfer/merge/create/offline-sync تحترم invariant نفسه. الحالات التي تسمح
  مستقبلًا بعدة Orders لمظلة/برجولة مؤجلة لـService Location في Gate 8؛ لا
  تفتح exception غير مدققة الآن.

---

## 3. شرائح التنفيذ

### Gate 4A — Settlement ledger وexactly-once payment

1. اكتب preflight inventory للـmodels/migrations/callers والبيانات المتعارضة.
2. صمم additive migration فقط للحد الأدنى المطلوب: settlement/idempotency/
   allocation أو امتداد Payment، source/original relation، actor fields،
   constraints/indexes. لا تنشئ جدولًا موازيًا يكرر Payment بلا تبرير الفرق
   الدلالي.
3. وحّد paid وsplit على service primitive واحدة ومعاملة واحدة.
4. اربط direct tenders بالـPayment والوردية والكاشير، وافصل room allocation.
5. أضف typed payment-method policy fail-closed بدل strings متعارضة.
6. حدّث API والـPOS client ليولدا/reuse idempotency key ويعرضا أخطاء shift/
   method/retry بوضوح.
7. لا تبدأ 4B قبل نجاح failure injection وPostgreSQL concurrency لـ4A.

### Gate 4B — Shift locking وreconciliation

1. partial unique open-shift invariant + lock helpers.
2. branch/ownership checks لكل shift endpoint.
3. cash movement effect contract والصيغة الكاملة للتوقع.
4. close serialization، manager-other-close reason/approval/audit.
5. إزالة التناقض بين `CashierShiftClose` و`ShiftPanel.vue` حول force-close.
6. تقرير نهاية الوردية يثبت كل مكوّن ولا يبتلع فشل بناء البيانات.

### Gate 4C — Order state/ownership/reversals/concurrency

1. state machine مركزية واختبارات transition table.
2. one-active-table-order invariant ومراعاة create/transfer/merge/offline.
3. creator/assigned waiter/item actor + waiter-transfer audit.
4. كل add/void/discount/refund/split mutation تستخدم lock order نفسه.
5. refund/void reversal references وstep-up المالي الدقيق.
6. historical receipt/OrderRead يعرض settlement breakdown من snapshot، ولا
   يعتمد على سعر Menu الحالي.

---

## 4. التوافق والهجرة

- حافظ على endpoints الحالية قدر الإمكان؛ يمكن توسيع bodies/headers وإضافة
  error codes. أي كسر مطلوب (مثل idempotency key الإلزامية للدفع) يُحدّث
  frontend في نفس الشريحة ويُذكر في التقرير.
- أبقِ `payment_method="room"` كـAPI compatibility alias إذا لزم، لكن حوّله
  داخل policy مركزية إلى دلالة واحدة؛ لا تخزن قيمتين لنفس المعنى.
- migrations إضافية فقط. لا تعديل migration تاريخية، لا حذف column/row، ولا
  backfill لـcashier/shift مجهول.
- أضف command/report قراءة فقط يسرد:
  - paid Dining orders بلا settlement/payment قابل للإثبات؛
  - duplicate active orders لكل table؛
  - duplicate open shifts؛
  - unknown payment methods/references؛
  - legacy correction movements بلا اتجاه.
- migration الجديدة يجب أن تنجح upgrade من head الحالي، downgrade للـhead
  السابق، ثم upgrade مرة أخرى على PostgreSQL معزولة. لو downgrade بعد بيانات
  جديدة يفقد دلالة، وثق أنه maintenance-only ولا تدّعي rollback آمنًا.

---

## 5. اختبارات إلزامية

### Payment / idempotency

- cash/card configured payment ينشئ settlement/Payment واحدًا بمبلغ صحيح،
  actor/shift/order/method صحيحين.
- لا direct tender بدون وردية مفتوحة لنفس الفرع.
- room charge لا يزيد shift cash ولا يتكرر عند folio settlement.
- نفس idempotency intent مرتين يعيد نفس النتيجة؛ intent مختلف يرفض.
- failure عند Payment/Folio/Inventory/COGS/GL/audit يعمل rollback كامل.
- paid-vs-paid وpaid-vs-split تحت PostgreSQL: نجاح منطقي واحد وآثار مرة واحدة.
- split rounding ومجموع allocations والjournal/folio/payment totals صحيحة.

### Shift

- open-vs-open لنفس الكاشير/الفرع: Shift واحدة فقط.
- branch A لا يفتح/يعرض/يغلق/report Shift فرع B.
- cash movements تدخل expected بالاتجاه الصحيح؛ drawer_open صفر؛ correction
  بلا اتجاه ترفض.
- close-vs-close: نجاح واحد، cash-count lines لا تتكرر.
- payment-vs-close: البيع إما داخل الوردية المقفلة بالكامل أو مرفوض بالكامل.
- manager close-other يحتاج السبب والحماية ويسجل actor/target.

### Order / reversal

- transition matrix تسمح الرحلات الصحيحة وترفض الرجوع/القفز غير الصحيح.
- create-vs-create على نفس table: نجاح واحد و409 واحد على PostgreSQL.
- transfer/merge لا يكسر active-order unique invariant.
- add/void/discount مقابل paid لا يترك total/payment mismatch.
- refund مرتين/متزامنًا لا يتجاوز refundable amount؛ reversal واحد مرتبط
  بالأصل، والفشل في Folio/GL يعمل rollback.
- waiter transfer يحفظ creator/old/new/actor/reason في audit.
- كل branch/role/permission failure يغطيه HTTP test، لا service unit فقط.

### Frontend

- idempotency key تظل نفسها خلال retry وتتغير لمحاولة جديدة فقط.
- shift-required / conflict / already-paid / method-not-configured / offline
  states واضحة ولا تعرض نجاحًا قبل server acknowledgement.
- أي component يتغير يستخدم `@resort-os/ui` وStaff i18n/formatters، ويضاف إلى
  ratchet المناسب. لا mass-translate لبقية التطبيق داخل Gate 4.

---

## 6. أوامر التحقق

اكتشف الأسماء النهائية للاختبارات، لكن الحد الأدنى:

```bash
bash scripts/agent-check.sh

cd backend
.venv/bin/pytest tests/test_api/test_dining_paid_atomicity.py \
  tests/test_api/test_refund_after_payment_http.py \
  tests/test_api/test_pos_full_cycle_http.py \
  tests/test_api/test_finance.py \
  tests/test_api/test_finance_http.py -v
.venv/bin/pytest tests/ -v
.venv/bin/alembic heads

# متغير DSN منفصل وقاعدة throwaway؛ الاسم النهائي يكتشف من harness الحالي
DINING_CONCURRENCY_TEST_ADMIN_URL=... .venv/bin/pytest \
  tests/test_dining_paid_concurrency.py tests/test_gate4_concurrency.py -v

cd ../frontend
pnpm --filter el-kheima validate:i18n
pnpm --filter el-kheima test:frontend
pnpm --filter el-kheima type-check
pnpm --filter el-kheima build
pnpm --filter public type-check
pnpm --filter public build

cd ..
git diff --check
git status --short --branch
```

ويلزم كذلك على PostgreSQL معزولة:

```text
upgrade من head السابق → head الجديد
downgrade إلى head السابق
upgrade إلى head الجديد
تشغيل preflight/reconciliation report
حذف قاعدة الاختبار بعد الإثبات
```

لا تكتب «passed» من JUnit total: اذكر `passed` و`skipped` و`failed` كل واحدة
منفصلة.

---

## 7. ملفات التسليم والتوقف

أنشئ/حدّث في النهاية:

- `docs/audits/gate-4-dining-payment-shift-order-integrity.md`
- `PROJECT_STATUS.md`
- `wagdy.md` بلغة بشرية
- `docs/audits/SMART_EXECUTION_ROADMAP.md`
- Project Cockpit snapshot
- migration notes + preflight/reconciliation output بلا بيانات شخصية

التقرير النهائي يذكر لكل شريحة:

- ما كان موجودًا وإعادة استخدامه؛
- root causes المؤكدة؛
- models/constraints/API التي تغيرت؛
- transaction وlock order؛
- idempotency contract؛
- mapping طرق الدفع وما ظل يحتاج تهيئة؛
- أثر migration والـrollback؛
- كل أمر ونتيجته الدقيقة؛
- المتبقي بصراحة.

**توقف إلزامي** إذا ظهر: duplicate active orders أو duplicate open shifts في
بيانات حقيقية تحتاج إغلاق/دمج، payment-method GL mapping إنتاجية لا يمكن
إثباتها، migration مدمرة، production secret، أو قاعدة محاسبية متعارضة. اعرض
الدليل والخيارات ولا تخمن.

بعد إكمال 4A→4B→4C والتحقق والمراجعة الذاتية: **توقف بلا commit ولا push ولا
بدء Gate 5/7/8**. Codex يراجع الـdiff كله مرة واحدة، يصلح الملاحظات المحدودة
عند الحاجة، ثم Mohamed يعتمد الـcheckpoint.
