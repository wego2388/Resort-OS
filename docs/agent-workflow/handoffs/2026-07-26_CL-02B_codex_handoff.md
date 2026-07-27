# CL-02B — Codex handoff

**التاريخ:** 2026-07-26  
**الحالة:** `READY_FOR_REVIEW` لعقد public contact/CRM/PII فقط.  
**بوابة النشر العامة:** `NO-GO` حتى معالجة استدعائي `DigitalHub.vue` القديمين المذكورين أدناه، وإغلاق CL-02C، واعتماد بيانات الحقيقة.  
**المشروعات:** `/home/wego/projects/resort-os` و`/home/wego/projects/elkheima-marketing-website`  
**التسليم:** لا commit، لا push، لا deploy.

## 1. النطاق وحدود الملكية

نُفذ:

- عقد typed وصارم لنماذج التواصل العامة.
- idempotency ومنع إساءة الاستخدام.
- تحديد الفرع من `Host` الموثوق فقط، بلا `branch_id` قادم من المتصفح وبلا fallback إلى الفرع 1.
- فصل إفصاح التواصل الخدمي الإلزامي عن موافقة التسويق الاختيارية.
- تشفير PII في ContactForm وCRM Lead مع forward migration واختبارات ترقية/خفض.
- retention وpurge وaudit خالٍ من PII.
- ربط submitters العامة خارج الشات بالعقد الجديد.

استُبعد عمدًا:

- `backend/app/core/**` وauth وملفات CX-02C/migration `b7e2c4a91f60`.
- chatbot وملفات CL-01.
- الملفات المملوكة لـCL-02A/CL-02D، باستثناء استخدام المكونات المشتركة التي لم تكن ضمن ملكيتها.
- إصلاح analytics/typecheck خارج CL-02B.

## 2. ما تم تنفيذه

### Backend

- `backend/app/modules/hub/schemas.py`
  - `extra=forbid`، حدود أطوال، رفض control characters، وتطبيع الهاتف والبريد.
  - يشترط وسيلة اتصال واحدة على الأقل.
  - `service_contact_authorized` يجب أن تكون `true`.
  - موافقة التسويق منفصلة وبنسخة إفصاح مستقلة.
  - `source_page` يقبل مسارًا نسبيًا فقط وhoneypot باسم `website`.
- `backend/app/modules/hub/public_contact.py`
  - يحل الفرع من `Host` عبر allowlist الإعداد الحالي، ويفشل مغلقًا عند host غير معروف.
  - HMAC digests لهوية الطلب وpayload؛ لا تُحفظ IP أو بيانات الاتصال الخام في audit.
  - حدود إساءة الاستخدام: 5 طلبات/IP خلال 10 دقائق و3/هوية اتصال خلال ساعة.
  - يفشل مغلقًا خارج development/test عند غياب Redis.
  - replay لنفس idempotency key وpayload يعيد نفس النتيجة، وتغيير payload يعيد 409.
  - ينشئ ContactForm للتواصل الخدمي، ولا ينشئ CRM Lead إلا بموافقة تسويق صريحة.
  - فشل مزامنة CRM لا يسقط الطلب الخدمي؛ يُسجل نوع الخطأ فقط دون PII.
- `backend/app/modules/hub/api/router.py`
  - body typed، و`Idempotency-Key` إلزامي بطول 16–128 ومحارف مقيدة، واستجابة 202 مع `no-store`.
- `backend/app/modules/hub/models.py` و`backend/app/modules/crm/models.py`
  - تشفير حقول الاسم والهاتف والبريد والموضوع/الرسالة/الملاحظات عبر `EncryptedString`.
  - حقول provenance، consent، retention، purge، sync status، وفهارس idempotency/retention.
- `backend/app/tasks/hub_tasks.py` و`backend/app/celery_app.py`
  - purge يومي محدود الدفعات في 03:30.
- `backend/alembic/versions/c4d8e2f6a901_public_contact_privacy_contract.py`
  - head جديد فوق `b7e2c4a91f60`.
  - يشفر البيانات القديمة plaintext في مكانها باستخدام `FIELD_ENCRYPTION_KEY` مع منع double encryption.
  - downgrade يفك تشفير legacy data ويستعيد العقد السابق، لكنه يرفض بأمان بعد وجود بيانات public جديدة أو purged.

### Frontend

- helper موحد typed في `src/api/publicContact.ts` يولد idempotency key ثابتًا لكل محاولة ويرسل نسخ الإفصاح.
- consent UI محلي ar/en/ru/it في `src/components/contact/PublicContactConsent.vue`:
  - إفصاح خدمي إلزامي مع رابط privacy.
  - opt-in تسويقي منفصل واختياري.
- رُبط العقد الجديد في:
  - `src/components/shared/PageBookingModal.vue`
  - `src/composables/booking/usePageBooking.ts`
  - `src/apps/public/Booking.vue`
  - `src/apps/public/Contact.vue`
  - `src/components/SunbedOrderModal.vue`
  - `src/components/hub/HubSpaSection.vue`
  - `src/components/hub/HubRoomServices.vue`
- أزيل الاعتماد على صورة TripAdvisor خارجية من `Contact.vue`.

## 3. Validation evidence

| الفحص | النتيجة |
|---|---|
| public contact + hub/blog API tests | PASS — 40 tests |
| CRM API/unit tests | PASS — 47 tests |
| PostgreSQL fresh Alembic chain | PASS — 3 tests |
| PostgreSQL CL-02B legacy encrypt/downgrade/re-upgrade | PASS — 2 tests |
| `alembic heads` | PASS — `c4d8e2f6a901 (head)` |
| backend `py_compile` للنطاق | PASS |
| marketing production build | PASS — 2039 modules |
| backend/frontend scoped `git diff --check` | PASS |

فحص `npm run type-check` يعمل الآن لكنه يبلغ فقط عن خطأين موجودين خارج هذا النطاق:

- `src/services/analytics.ts:148` — TS2774
- `src/services/analytics.ts:170` — TS2774

لم تُعد الاختبارات في لحظة التجميد؛ النتائج أعلاه هي آخر تشغيل ناجح في نفس جلسة العمل. تعذر فحص أسماء قواعد الاختبار المؤقتة في لحظة التجميد لأن PostgreSQL المحلي لم يكن يستمع على `127.0.0.1:5432`.

## 4. عائق النشر المعروف

ما زال في `src/apps/public/DigitalHub.vue` استدعاءان مباشران للعقد القديم:

- السطر التقريبي 733: complaint
- السطر التقريبي 939: rating

الملف ضمن نطاق chatbot/CL-01 المستبعد، لذلك لم يُعدل. الاستدعاءان لا يرسلان contact identity أو disclosure consent أو idempotency key، وبالتالي سيعيد backend الصارم 422. لا ينبغي تخفيف عقد الأمان لمعالجتهما.

قبل نشر Digital Hub يجب على مالك الشات اختيار أحد الحلين:

1. عقد complaint/rating خاص مرتبط بجلسة الضيف الموثقة ولا يدعي marketing contact، أو
2. واجهة إفصاح خدمي واضحة + وسيلة اتصال + idempotency وفق العقد الجديد.

## 5. متطلبات الإنتاج

- ضبط host الإنتاجي حرفيًا في `CHAT_PUBLIC_HOST_BRANCH_MAP` وربطه بالفرع الصحيح؛ لا wildcard ولا fallback.
- ضمان Redis صحي قبل فتح endpoint العام.
- تثبيت `FIELD_ENCRYPTION_KEY` الصحيح، نسخه احتياطيًا، ومنع تغييره بعد الترحيل.
- تشغيل Celery worker وbeat والتحقق من purge job.
- اعتماد مسؤول البيانات لمدة retention وسياسة الحذف.
- اعتماد نص privacy ووسيلة إلغاء الموافقة التسويقية/التواصل.
- تنفيذ staging smoke/UAT مع host الحقيقي ثم فحص عدم ظهور PII في logs وAuditLog.

## 6. قرار التسليم

تنفيذ CL-02B نفسه جاهز للمراجعة، لكن الإطلاق العام يظل `NO-GO` حتى إصلاح استدعائي DigitalHub، وإغلاق CL-02C، واعتماد متطلبات الإنتاج أعلاه. الشجرة تُركت كما هي دون commit أو push أو deploy، وتغييرات agents الأخرى محفوظة ولم تُنسب لهذا packet.
