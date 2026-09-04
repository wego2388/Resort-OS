# Decision 0005: Personal Credit Account (حساب آجل شخصي)

- **Decision status:** Accepted.
- **Implementation status:** Implemented, deployed, and production-verified on
  2026-08-08 after Mohamed's approval. Active release `1d77e7b`; production
  Alembic `c9d4e5f6a7b8 (head)`.
- **Date:** 2026-08-08
- **Owner:** Mohamed
- **Product:** El Kheima Beach Resort OS

## Context

العميل أو الموظف المسجّل يمكن أن يكون له حساب آجل مفتوح بلا مدة
`check-in/check-out`. يمكن ترحيل مبيعات Dining وBeach عليه، ثم تحصيله
نقدًا أو بنكيًا لاحقًا. المحاسب والمدير يديران الحساب وكشفه من
Staff App، والمالك يرى الإجمالي والتفاصيل قراءةً فقط.

هذا الحساب ليس `Folio` لنزيل مقيم، وليس `B2BContract` لشركة، وليس
`CustomerGroup` للخصم. خصم مجموعة العميل يظل مصدره الحالي، ثم يُرحّل
إجمالي البيع النهائي من مصدر الحقيقة في Dining/Beach على الحساب.

## Correction to the original draft

النسخة الأولى من القرار اقترحت GL `1200` للذمم الشخصية. هذا غير صحيح في
دليل حسابات المشروع، لأن `1200` مستخدم بالفعل **للمخزون** ويدخل في قيود COGS.
القرار المنفّذ هو:

- `1160` — Personal Credit Receivables / ذمم حسابات آجلة شخصية.
- `1150` يظل لذمم الفوليو.
- `1200` يظل للمخزون دون أي تغيير.

تضيف الـmigration الحساب `1160` للفروع الموجودة، ويضيفه `seed.py` أيضًا
لبيئات الجديدة.

## Data model

### `CreditAccount`

- branch-scoped، ومملوك لـ`Customer` أو `Employee` واحد بالضبط.
- DB constraints تفرض XOR وتطابق `holder_type` مع الـFK الممتلئ.
- حساب واحد فقط لنفس الشخص في نفس الفرع.
- `credit_limit >= 0`؛ الصفر يعني بلا حد.
- `current_balance >= 0` projection للأداء؛ المصدر القابل لإعادة الحساب هو
  مجموع `CreditTransaction.balance_delta`.
- الحالة: `active | suspended | closed`.

### `CreditTransaction`

حركة دفتر أستاذ غير قابلة للتعديل أو الحذف:

- `charge`: `balance_delta = +amount`، وله مرجع Dining أو Beach واحد فقط.
- `payment`: `balance_delta = -amount`، وطريقة `cash | bank`.
- `refund`: `balance_delta = -amount`، ويرتبط بعملية `charge` أصلية؛ يسمح
  بأكثر من مرتجع صنف مع منع مجموعها من تجاوز مبلغ البيع.
- `reversal`: يعكس `balance_delta` وسطور القيد الأصلي بالضبط.
- `journal_entry_id` غير nullable لكل حركة، بما فيها العكس.
- unique source لمنع ترحيل نفس Order/BeachTransaction مرتين.
- unique branch-scoped idempotency key. خدمة العكس تمنع أي عكس ثانٍ، كما
  تمنع العكس الكامل بعد بدء مرتجعات تجارية على نفس البيع.
- الـFKs المالية `RESTRICT`؛ لا يوجد DELETE endpoint.

## Accounting contract

### Charge

```text
Dr 1160  Personal credit receivables       final tender amount
Cr <outlet revenue account(s)>             same amount
```

- Dining يستخدم `Outlet.revenue_account_code` ويدعم cross-outlet في **قيد واحد
  متعدد السطور**. الكود الافتراضي الحالي للمنفذ `4200`.
- Beach يرحّل على `4300` ويحمّل `total_amount + vat_amount`، لا الصافي دون
  الضريبة.
- لا يُنشأ `Payment` نقدي ولا `FolioCharge` للجزء الآجل.

### Collection

```text
Cash: Dr 1100 Cash / Cr 1160 Personal receivables
Bank: Dr 1110 Bank / Cr 1160 Personal receivables
```

### Reversal

يتم إنشاء JournalEntry جديدة تبدّل debit/credit لكل سطر من القيد الأصلي.
لا يمكن عكس reversal، أو عكس الأصل مرتين، أو عكس تحصيل إذا كان سيجعل الرصيد
سالبًا.

### Sale refund

مرتجع Dining الجزئي لا يُعامل كتحصيل cash ولا كعكس كامل للبيع. ينشئ حركة
`refund` وقيدًا بنسبة tender الآجل:

```text
Dr <revenue account of the refunded item>   refunded credit share
Cr 1160 Personal credit receivables         same amount
```

مرتجعات الأصناف المتعددة مقفولة على حركة البيع الأصلية، ومجموعها لا يتجاوز
الـcharge. آخر مرتجع يمتص فروق التقريب. إذا كانت تحصيلات لاحقة ستجعل الرصيد
سالبًا يفشل المرتجع ويطلب تسوية يدوية بدل صناعة رصيد دائن وهمي.

## Transaction and concurrency contract

1. تقفل خدمة الحساب صف `CreditAccount` بـ`SELECT ... FOR UPDATE NOWAIT`
   مع `populate_existing=True` قبل فحص الحالة والرصيد والحد.
2. PostgreSQL SQLSTATE `55P03` فقط يتحول إلى conflict قابل للمحاولة؛ أي
   `OperationalError` آخر يصعد كخطأ DB حقيقي.
3. Dining settlement وBeach sale يستدعيان credit service بـ`commit=False` داخل
   نفس unit of work. الـcommit والـrollback يشملان البيع، السعة/المخزون،
   الحركة، الرصيد، والقيد معًا.
4. Beach void يعكس حركة الحساب الآجل وقيدها بدل إنشاء عكس كاش وهمي. Dining
   item refund يوزّع المبلغ على tender الآجل وبقية الـtenders في نفس معاملة
   الطلب، مع rollback كامل لأي فشل.
5. إعادة نفس idempotent intent ترجع النتيجة نفسها؛ استخدام المفتاح لنية مختلفة
   يُرفض.

## Business rules

1. المبلغ المرحّل هو tender النهائي المحسوب من Dining/Beach بعد قواعد
   الخصم الحالية، وشامل الضريبة/الخدمة حسب مصدر البيع.
2. `active` فقط يقبل charge. `suspended` يرفض charge ولكن يقبل collection.
   `closed` لا يُسمح به إلا عند رصيد صفر.
3. لا يمكن خفض `credit_limit` أقل من الرصيد الحالي.
4. تجاوز الحد fail-closed. الكاشير يحتاج PIN مدير صالح لـ
   `override_credit_limit`; manager+ يقر القرار بصلاحيته. كل override يُسجل في audit.
5. يمكن الاختيار من POS كحساب `customer` أو `employee`. إرسال
   `credit_account_id` يُفحص ضد الفرع؛ حساب العميل يجب أن يطابق عميل Dining/Beach
   المربوط، أما حساب الموظف فيُربط مباشرة بمرجع البيع.
6. البيع الآجل في Beach online-only، ولا يدخل offline queue. تسمح الشاشة بنوع
   تذكرة واحد في العملية الآجلة لتجنب partial multi-request sale.

## Authorization

| Operation | Exact roles / policy |
|---|---|
| POS lookup | cashier+ مع `credit.accounts.lookup` |
| Charge | cashier+ مع `credit.transactions.charge` |
| Create/status | `manager | admin | super_admin` |
| Change limit | `admin | super_admin` |
| Collect | `accountant | manager | admin | super_admin` |
| Statement/list | `accountant | manager | admin | super_admin` |
| Reverse | `manager | admin | super_admin` |
| Owner cockpit | `owner` read-only عبر owner API فقط |

الـexact-role dependency موجودة بجوار permission matrix؛ لذلك `hr_manager` لا يأخذ صلاحية
مالية لمجرد أن role level لديه مرتفع. `owner` لا يستطيع الكتابة على credit API.
`branch_id` لا يأتي من body؛ يُؤخذ من active branch context.

## API

```text
POST  /credit/accounts
GET   /credit/accounts                         paginated
GET   /credit/accounts/lookup                  customer|employee + holder_id
GET   /credit/accounts/{id}
PATCH /credit/accounts/{id}/status
PATCH /credit/accounts/{id}/limit
POST  /credit/accounts/{id}/charge
POST  /credit/accounts/{id}/payment
POST  /credit/accounts/{id}/reverse
GET   /credit/accounts/{id}/statement

GET   /owner/credit-receivables                owner read-only
```

كل credit response، بما في ذلك 4xx/5xx، يحمل `Cache-Control: no-store, no-cache,
must-revalidate, private`. القوائم paginated، والردود المالية تحمل `computed_at`.

## User interfaces

### Staff App

- route: `/admin/credit-accounts`.
- قائمة paginated مع فلاتر holder/status، فتح حساب، كشف، تحصيل cash/bank،
  تعليق/إغلاق، تعديل limit للـadmin، وعكس حركة. كشف الحساب يميّز مرتجع البيع
  ولا يعرض له زر عكس يدوي.
- Dining POS يدعم tender آجلة كاملة أو split، للعميل أو الموظف.
- Beach POS يعرض الرصيد والمتاح، ويدعم العميل/الموظف وPIN override.
- Arabic/English strings موجودة للشاشات وحالات الخطأ.

### Owner App

- `NowScreen` يعرض `credit_account_outstanding` و`credit_account_count`.
- قائمة تفصيلية تشمل active وsuspended balances، آخر charge، وoverdue flag.
- لا يوجد أي write action للمالك.

## Verification record

نُفذت تغطية لـ:

- charge / cash-bank collection / sale refund / exact reversal وتطابق projection
  مع ledger sum.
- تجاوز الحد fail-closed، suspended/closed lifecycle، duplicate holder، idempotency،
  single reversal، pagination، owner totals.
- NOWAIT contention وعدم إخفاء DB operational failures غير الخاصة بالقفل.
- Dining وBeach integration لحسابات customer وemployee، وعدم إنشاء cash
  `Payment` للآجل.
- Beach final amount (VAT is zero under Decision 0006)، وatomic rollback
  للتذكرة/السعة/الرصيد عند فشل GL.
- Beach credit void بلا cash artifacts، وDining credit item refund الكامل/
  الجزئي مع cap وتجميع صحيح لفروق التقريب.
- exact-role authorization، owner/hr_manager/cashier denials، branch isolation، no-store.
- PostgreSQL 16 fresh-chain `upgrade head`، downgrade لهذه المراجعة، ثم upgrade؛
  Alembic head واحد `c9d4e5f6a7b8`.
- 21/21 اختبارات قبول القرار و242/242 لاختبارات Credit + Dining + Beach
  المركزة، بما فيها split cash/credit وثلاثة مرتجعات مع cumulative rounding.

التشغيل الخلفي الكامل جمع 2565 اختبارًا، وصل 100% بـexit 0 وصفر failure.
نتائج الـfrontend والـmigration وبقية البوابات مسجلة في handoff قبل النشر.

## Deployment state

وافق Mohamed على النشر، وطُبقت الـmigration
`f8aa1f0fabba -> c9d4e5f6a7b8` على الإنتاج بعد dump متحقق وrollback tags.
الإصدار الفعال `/opt/resort-os-releases/1d77e7b` (implementation `dd26a1f`)،
والخدمات المتغيرة سليمة بلا restarts. جداول الحسابات والحركات بدأت فارغة،
والفرع الفعال لديه GL `1160`. فحوصات health/ready والنطاقات الأربعة وNginx
وsystemd healthcheck نجحت، ولم تُنشأ حركة مالية تجريبية على بيانات الإنتاج.

تفاصيل النسخ والبصمات والصور ونتائج الـsmoke مسجلة في
`docs/agent-workflow/handoffs/2026-08-08_CREDIT-0005_codex_handoff.md`.

## Revision history

- 2026-08-08: قبول الاتجاه الأول.
- 2026-08-08: مراجعة التنفيذ؛ تصحيح GL من `1200` إلى `1160`، وتثبيت
  الـatomicity، locking، idempotency، reversal، exact roles، customer/employee POS، وحالة
  التنفيذ الفعلية.
- 2026-08-08: موافقة Mohamed والنشر على production؛ migration إلى
  `c9d4e5f6a7b8`، active release `1d77e7b`، ونجاح health/smoke/log gates.
