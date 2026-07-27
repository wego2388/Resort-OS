# مراجعة Codex المستقلة — CL-01

- **Reviewer:** Codex
- **Implementer:** Claude
- **التاريخ:** 2026-07-26
- **النطاق:** موديول `backend/app/modules/chat/**` وتكامله مع
  `elkheima-marketing-website`
- **النتيجة:** **CHANGES_REQUESTED**
- **Commit / push / VPS writes:** لم يحدث

## الخلاصة

التنفيذ الأساسي جيد ويحل مشكلة حقيقية: عقد الـAPI أصبح موجودًا، تكامل الموقع
معه يعمل، الهجرة لها head واحد، وحدود الأحجام والـtimeout والـcircuit breaker
موجودة، وإصلاح escape-then-format في `ChatbotMessage.vue` يمنع إدخال HTML من
نص رد النموذج في الحالة الحالية.

لكن الحزمة ليست مقبولة للإنتاج بعد. توجد خمسة blockers عالية الأولوية؛ أهمها
أن دفاع prompt injection الحالي يمكن تجاوزه من `history`، وأن الرسالة الحالية
تصل للنموذج خامًا من `history` قبل أن يفيد تنظيف `message`. كذلك توجد ادعاءات
تسويقية غير معتمدة، `branch_id=1` ثابت، وسياسة الخصوصية/الاحتفاظ لم تُحسم رغم
تخزين النص الحر وإرساله إلى طرف ثالث.

## ما تم قبوله في التنفيذ

- العقد الأساسي للمسارات الأربعة متوافق بين الـBackend والواجهة.
- حدود Pydantic للرسالة والتاريخ واللغة موجودة.
- timeout واضح وترجمة أخطاء المزود إلى حالات HTTP معقولة.
- حد الدقيقة والسقف اليومي والـcircuit breaker تحسينات صحيحة في الاتجاه.
- الـHTML escaping يسبق تحويل Markdown المحدود، ولا يظهر مسار HTML مباشر من
  رد Gemini في التنفيذ الحالي.
- migration لها Alembic head واحد، وجداولها تتطابق إجمالًا مع الـmodels.
- حذف widget المكرر وإصلاح مسارات `/api/v1/chat` صحيحان.

## [High] نتائج تمنع قبول CL-01

### H-01 — `history` يتجاوز دفاع prompt injection، والرسالة الحالية تُرسل مرتين

**الدليل**

- `useChatbot.ts:253-259` يضيف رسالة المستخدم إلى `messages` قبل استدعاء
  `getGeminiResponse()` في `:272`.
- `useChatbot.ts:472-486` يبني `history` من آخر الرسائل، لذلك يحتوي على الرسالة
  الحالية الخام، ثم يرسلها مرة ثانية في حقل `message`.
- `chat/api/router.py:56` ينظف `req.message` فقط، بينما `:59` يمرر كل
  `req.history` كما أرسله العميل.
- `chat/services.py:253-256` يضع التاريخ غير الموثوق في payload المزود، ثم
  يضيف الرسالة الحالية.
- `location_type` و`location_number` أيضًا يدخلان تعليمات النموذج من دون
  تطبيع مناسب؛ `location_number` يسمح بسطر جديد ونص توجيهي.

هذا يعني أن رسالة مثل `ignore previous instructions` يمكن تحويلها إلى
`"سؤال غير صالح"` في `message`، بينما تظل النسخة الأصلية موجودة في `history`
وتصل إلى Gemini. ويمكن لأي عميل معدل إرسال `history` مصطنع بدور `model`.
القائمة السوداء لعبارات محدودة ليست boundary أمنيًا حتى بعد سد هذا المسار.

**الإصلاح المطلوب**

1. لا يُقبل تاريخ المحادثة من العميل كمصدر موثوق.
2. بعد إنشاء جلسة server-issued، يستعيد الـBackend آخر الأدوار المملوكة للجلسة
   من قاعدة البيانات، أو يعمل turn بلا history إن لم توجد جلسة.
3. استخدام حقل `systemInstruction` الحقيقي في عقد Gemini بدل تمثيل التعليمات
   كأول رسالة `user`.
4. اشتقاق location من guest session موثقة على الخادم؛ لا تُحقن query values
   مباشرة في تعليمات النموذج.
5. إضافة اختبارات تثبت أن:
   - الرسالة الحالية تظهر مرة واحدة فقط في provider payload.
   - history مصطنع أو role مزور لا يصل للمزود.
   - injection داخل message/history/location لا يصبح instruction موثوقًا.

### H-02 — عبارة “لا PII يُرسل” غير صحيحة، ولا توجد سياسة احتفاظ إنتاجية

إزالة `guest_phone` و`user_name` من `ChatContext` خطوة جيدة، لكنها لا تمنع
الضيف من كتابة اسمه أو هاتفه أو بريده داخل نص الرسالة.

**مسار البيانات الحالي**

- النص والتاريخ يُرسلان إلى Gemini في `services.py:249-270`.
- النص والرد يُخزنان plaintext في `chat_messages.message`
  (`models.py:49-56` و`router.py:76-80`) بلا مدة احتفاظ أو job للحذف.
- الواجهة تحفظ التاريخ كاملًا في `localStorage`
  (`useChatbot.ts:403-412`).
- المسار الموجود مسبقًا في `useChatbot.ts:314-318,581-594` يرسل رسالة
  “lead” تلقائيًا إلى CRM أو يحفظها محليًا، بلا اختيار صريح من الزائر.

**الإصلاح/القرار المطلوب قبل الإنتاج**

1. تعديل نصوص handoff/comments/tests حتى لا تدعي أن غياب حقول الهوية يعني
   غياب PII.
2. إظهار إشعار خصوصية واضح قبل أول turn يشرح إرسال النص لمزود AI.
3. اعتماد المالك لمدة الاحتفاظ، وهل التخزين مطلوب أصلًا؛ الافتراضي الآمن هو
   عدم حفظ raw text إلا لغرض معتمد.
4. عند اعتماد التخزين: تشفير مناسب، حذف دوري فعلي، وحق حذف/مسح الجلسة.
5. منع lead capture الصامت؛ التحويل إلى CRM يكون بفعل واضح من المستخدم وبحقول
   typed، وليس نسخ رسالة الدردشة تلقائيًا.
6. توثيق وضبط إعدادات logging/data sharing في مشروع Gemini قبل الإنتاج.

مرجع المزود الرسمي: GenerateContent لا يخزن الطلبات افتراضيًا إلا إذا فُعل
logging على مستوى المشروع، لكن إعدادات المشروع قابلة للتغيير؛ لذلك يلزم
preflight موثق، لا افتراض برمجي فقط:
`https://ai.google.dev/gemini-api/docs/logs-datasets`.

### H-03 — الـprompt ينشر حقائق غير معتمدة ويخالف Gate 4

`services.py` يضيف أو يفترض:

- تصنيف “5 نجوم” في `:36-37` و`:175-178`.
- رقمًا وعنوانًا fallback في `:158-159`.
- طرق دفع ثابتة في `:190`.
- إلغاء مجاني قبل 3 أيام افتراضيًا في `:162,191`.
- أسعارًا بعد تحويل Decimal إلى `int` في dining/beach/rooms، ما قد يغيّر
  القيمة الفعلية ويحذف الكسور.
- عدد الغرف ذات الحالة التشغيلية `available` حاليًا على أنه معلومة بيع عامة؛
  هذا ليس availability مبنيًا على تواريخ إقامة.
- رسالة ندرة “قبل ما تخلص” في `:136-141`.

هذا يخالف صراحة
`EL_KHEIMA_FINAL_EXECUTION_PLAN_AR.md:326-343` الذي يمنع ادعاء 5-star أو
سعر/حقيقة غير معتمدة.

**الإصلاح المطلوب**

- الحقائق العامة تأتي فقط من public content facts بحالة `approved` وغير
  منتهية؛ إن غابت الحقيقة تُحذف من الـprompt بدل fallback مخترع.
- لا يعرض تصنيفًا أو سياسة إلغاء أو طرق دفع قبل اعتمادها.
- تنسيق Decimal بلا truncation مع العملة وحالة الضريبة وفترة الصلاحية.
- عدم تسمية room status اللحظي availability للحجز؛ يلزم تاريخا وصول ومغادرة
  وعقد PMS فعلي، أو توجيه الضيف للاستعلام دون أرقام ندرة.

### H-04 — الفرع والموقع غير مشتقين من مصدر server-side موثوق

- كل المسارات تستخدم `_DEFAULT_BRANCH_ID = 1`
  (`chat/api/router.py:15-18`).
- إذا لم يوجد branch رقم 1، بدء المحادثة يمكن أن يفشل بـFK 500.
- في بيئة متعددة الفروع ستُعرض بيانات الفرع الخطأ.
- `DigitalHub.vue:631-637` يرجع إلى `route.query.type/id` عندما لا توجد
  guest location موثقة، ثم `:1091-1092` يرسلها للشات.

هذا يخالف عقد الخطة: تحديد الفرع من host/slug على الخادم، لا `branch_id=1`.

**الإصلاح المطلوب**

- بناء/استخدام public bootstrap يربط host/site slug بفرع حقيقي.
- تخزين branch المختار مع الجلسة server-side وعدم قبوله من الزائر.
- تمرير guest-session bearer/token إلى الـBackend، واشتقاق location منه فقط.
- fail closed برسالة إعداد واضحة إذا لم يوجد site/branch mapping.
- اختبارات branch A/B واختبارات location query مزورة.

### H-05 — حماية التكلفة حسب IP فقط ولا تحقق شرط الخطة

الخطة تطلب حدودًا مستقلة حسب IP وguest/session مع سقف تكلفة. التنفيذ يملك:

- 20/دقيقة حسب IP.
- 300/يوم حسب IP.
- لا حد للجلسة، ولا global provider budget، ولا حد concurrency.

على شبكة المنتجع قد يشترك ضيوف كثيرون في public IP واحد، فيستطيع مستخدم واحد
استهلاك حصة الجميع. وعلى العكس، شبكة botnet تتجاوز سقف IP بسهولة. كما أن
Redis إذا تعطل يرجع بصمت إلى ذاكرة العملية، فلا يكون السقف موزعًا بين أكثر
من worker.

**الإصلاح المطلوب**

- IP burst limit + session limit + global daily token/cost budget.
- القيم داخل `Settings` مع production preflight.
- Redis مطلوب fail-closed لحماية التكلفة في production، أو limiter مركزي
  بديل موثق.
- metrics: requests، input/output tokens، 429، provider errors، estimated cost.
- حد واضح للتوازي مع fallback بلا نداء للمزود عند امتلائه.

## [Medium] نتائج مطلوبة أو تُسجل كدين مقبول صراحة

### M-01 — session ID ليس إثبات ملكية

العميل يختار `session_id`، وstart يعيد success إذا كان موجودًا، و`/chat`
يستطيع الإضافة لأي conversation معروف، و`/end` يستطيع إنهاءه/تقييمه. لا يوجد
read endpoint، لذلك الخطر الحالي أساسه integrity لا تسريب القراءة، لكنه يظل
عقدًا ضعيفًا.

المطلوب: session reference يصدره الخادم مع bearer secret منفصل أو token موقع،
UUID/schema صارم، فحص `status == active`، rate limit لمسار end، وعدم إظهار
session في URL إن أمكن.

### M-02 — تكامل Gemini غير ثابت للإنتاج

- المفتاح موضوع في query string (`services.py:262`)؛ عقد Gemini الرسمي الحالي
  يطلب `x-goog-api-key`.
- القيمة الافتراضية `gemini-flash-latest` alias متحرك. توثيق Google يوصي
  بإصدار stable محدد لمعظم تطبيقات الإنتاج.
- `temperature` و`topP` أصبحا deprecated للموديلات الجديدة.
- canned `model` priming turn ليس بديلًا لـ`systemInstruction`.

المطلوب: header للمفتاح، model stable pinned بعد eval، system instruction
رسمي، وإزالة المعاملات/الأدوار غير المدعومة للموديل المختار. المراجع:
`https://ai.google.dev/api`,
`https://ai.google.dev/gemini-api/docs/models`,
`https://ai.google.dev/gemini-api/docs/latest-model`.

### M-03 — دورة حياة المحادثة والتقييم غير مكتملة

- start يسجل اللغة `ar` دائمًا تقريبًا بدل `locale.value`
  (`useChatbot.ts:142`).
- `rateConversation()` لا يرسل rating للـBackend (`:383-393`).
- `close()` يحذف session ID لكنه يبقي الرسائل؛ إعادة الفتح لا تبدأ جلسة جديدة
  لأن `messages.length !== 0`.
- check-then-create في start معرض لسباق unique constraint.
- حفظ user/model يتم في commitين منفصلين، فيمكن ظهور نصف turn.

المطلوب: state machine واضحة، start idempotent ذري، rating حقيقي، restart
صحيح، وtransaction واحدة لزوج الرسائل.

### M-04 — روابط action لا تحقق allowlist/`noopener`

`ChatbotMessage.vue:116-121` يمرر `action.value` إلى `router.push` أو
`window.open` بلا scheme/host allowlist وبلا `noopener,noreferrer`.
صحيح أن رد الـBackend الحالي لا ينشئ actions، لكن history المحمل من
`localStorage` غير typed runtime، والـcomponent نفسه جزء من سطح الشات.

المطلوب: قبول routes داخلية معروفة فقط، و`https/http/tel` وWhatsApp المعتمد
حسب المنتج، وفتح الخارجي بـ`noopener,noreferrer`. أضف اختبارات
`javascript:`, `data:`, protocol-relative URL، وroute خارجي.

### M-05 — لا توجد سياسة `Cache-Control: no-store` صريحة

أضف `no-store` لاستجابات chat/conversation العامة، واختبره كما يطلب Gate 2.

## [Low] تحسينات صغيرة

- DB checks لقيم `role/status/language` بدل الاعتماد على مسار API وحده.
- index مناسب لـ`(branch_id, created_at/status)` قبل بناء analytics.
- schema موحد للغة welcome بدل قبول أي string والرجوع للعربية بصمت.
- إعادة استخدام `httpx.AsyncClient` بحدود connections بدل إنشائه لكل turn.
- فحص `finishReason` وsafety/block responses، وtrim/حد منطقي للرد قبل التخزين.

## ملاحظات تُنقل إلى CL-02 / CL-03 ولا تُنسب وحدها إلى CL-01

- lead capture الصامت والكوبونات الثابتة
  (`SUMMER25/HONEYMOON30/...`) يجب إيقافها حتى اعتماد حقائق المحتوى والموافقة.
- موقع التسويق ما زال يحمل منطق staff token/refresh في عميل API العام.
- Nginx الخاص بالموقع يحتاج CSP وباقي security headers.
- `npm audit --omit=dev` يعرض 3 ثغرات في شجرة `unhead`
  (2 low، 1 moderate) وتحتاج ترقية مدروسة لا `--force` عمياء.
- أداة typecheck نفسها مكسورة حاليًا بسبب عدم توافق `vue-tsc` القديم مع
  TypeScript المثبت؛ نجاح Vite build لا يعوض typecheck.

## التحقق المستقل الذي نفذه Codex

```text
backend/.venv/bin/pytest -q tests/test_api/test_chat.py
→ 42 passed

backend/.venv/bin/alembic heads
→ dc6bfb5b79e8 (head)

python -m compileall -q app/modules/chat
→ pass

npm run build
→ pass (2036 modules)

npm run type-check
→ fail داخل vue-tsc:
  Search string not found: "/supportedTSExtensions = .*(?=;)/"

npm audit --omit=dev
→ 3 vulnerabilities (2 low, 1 moderate)
```

لم يُعد Codex تشغيل 2126 اختبارًا كاملًا؛ نتيجة Claude الكاملة موثقة في
handoff، بينما التحقق أعلاه هو التحقق المستقل المحدد لنطاق المراجعة.

## شروط إعادة التقديم

1. معالجة H-01 إلى H-05 واختبارها.
2. معالجة M-01 إلى M-05 أو تسجيل قرار مالك واضح بقبول الدين مع موعد وحزمة.
3. عدم تعديل ملفات CX-02A/CX-03 الخاصة بـCodex.
4. إعادة تشغيل chat tests + regression مناسب + migration check + marketing
   build/typecheck بعد إصلاح toolchain.
5. إنشاء handoff محدث لـ`CL-01R` يربط كل finding بالإصلاح والاختبار.
6. لا commit ولا push قبل مراجعة Codex الثانية وقرار المالك.

