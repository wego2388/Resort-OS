# HUB-CATALOG-01 — خطة كتالوج المنتجات + دفع Paymob على الموقع العام

> **حالة الوثيقة:** `DRAFT — OWNER APPROVAL REQUIRED`
> **حالة التنفيذ:** `NOT STARTED — ينتظر Approval A`
> **المالك وصاحب قرار البدء:** Mohamed
> **قائد التنفيذ والمراجع النهائي:** Codex
> **تاريخ الإعداد:** 2026-08-07
> **Resort OS baseline:** `427ae82` على `claude/CX-02C-frontend-auth-bootstrap`
> **Marketing baseline:** آخر commit على `main` في `elkheima-marketing-website`
> **الإنتاج الحالي:** Resort `427ae82`، Marketing `bc48f09`

هذه وثيقة تنفيذ كاملة قابلة للتحويل إلى حزم عمل بعد اعتماد Mohamed.
**ليست إذنًا بالتنفيذ أو commit أو push أو deploy أو migration أو تعديل
بيانات أو أسعار**. لوحة التنفيذ `EL_KHEIMA_EXECUTION_BOARD.md` هي
مصدر المهمة الجارية، ولا تُضاف هذه الحزمة إليها إلا بعد الاعتماد الصريح.

---

## 0. بوابات موافقة المالك

### Approval A — بدء التطوير

العبارة المقترحة:

> أوافق على بدء تنفيذ HUB-CATALOG-01 وفق الخطة. الأسعار لا تُنشر للعموم
> قبل Approval B المنفصلة. لا نشر على الإنتاج قبل Approval C.

تسمح بـ: كتابة الكود + migrations + tests محليًا، بناء واجهة الإدارة،
ربط الموقع بالـ API في بيئة غير منشورة.

لا تسمح بـ: تشغيل migration على الإنتاج، نشر أسعار حقيقية، تعديل
`PUBLIC_TRUTH.publish.prices`، أي تغيير على VPS.

### Approval B — نشر الأسعار للعموم

موافقة مستقلة تحدد: الفئات المسموح بها (أنشطة؟ باقات؟ كلاهما؟)،
مصدر كل سعر ومن اعتمده، تاريخ السريان.

### Approval C — النشر على الإنتاج

بعد نجاح UAT كامل وتقديم أدلة الاختبار.

---

## 1. النتيجة التجارية المطلوبة

يستطيع المدير من داخل `app.elkheima.com` أن:
1. يضيف باقة/نشاط/فعالية/خدمة شاطئ بالاسم والسعر والوصف والصور بأربع لغات.
2. يفعّل/يوقف أي منتج فيظهر أو يختفي فورًا من الموقع **بدون لمس كود**.
3. الزائر على `elkheima.com` يرى كارت المنتج، يضغط "احجز"، يدفع فيزا/ماستر أو
   فودافون كاش عبر Paymob، والحجز يُسجَّل تلقائيًا في البرنامج.

---

## 2. الوضع الحالي — ما وجدناه في الكود

### ما هو موجود ويُعاد استخدامه

| الملف | ما يفيدنا |
|---|---|
| `hub/models.py` — `HubOffer` | جدول عروض مؤقتة موجود — **لا نكسره**، الكتالوج جدول منفصل |
| `hub/models.py` — `HubOnlineBooking` | استقبال الحجوزات + ربط بـ PMS عند التأكيد ✅ |
| `hub/services.py` — `create_online_booking` | منطق التحقق من العرض + `increment_offer_bookings` ✅ |
| `hub/services.py` — `confirm_booking` | ينشئ PMS booking تلقائيًا عند التأكيد ✅ |
| `hub/api/router.py` — `_assert_hub_branch` | branch isolation موجود ✅ |
| `hub/api/router.py` — `/hub/contact` | idempotency + rate-limit pattern ✅ — نتبعه في Paymob webhook |
| `hub/crud.py` — `list_offers` | `local_today()` بدل `date.today()` ✅ — نفس النمط في الكتالوج |
| `HubManagementView.vue` | صفحة إدارة Hub موجودة — نضيف تاب "الكتالوج" |
| `usePageBooking.ts` | composable الحجز من الموقع — نوسّعه للـ checkout |
| `backend/.env.example` | `PAYMOB_API_KEY`, `PAYMOB_CARD_INTEGRATION_ID`, `PAYMOB_VODAFONE_INTEGRATION_ID` — متوقعة فعلاً ✅ |

### الفجوات الحقيقية

| الفجوة | الحل |
|---|---|
| لا يوجد endpoint عام للكتالوج (بدون auth) | `GET /hub/catalog/public` جديد |
| `HubOffer` للعروض المؤقتة فقط — مفيش كتالوج دائم | جدول `hub_catalog_items` جديد |
| `HubOnlineBooking` لا يعرف حالة "في انتظار الدفع" | إضافة `payment_pending` / `payment_failed` لـ status |
| Paymob غير مبني (config موجود في .env.example فقط) | `app/resort_os/paymob_gateway.py` جديد |
| الموقع يعرض بيانات ثابتة من i18n | استبدال بـ API call + fallback ثابت |

---

## 3. التصميم التقني الكامل

### 3.1 جدول `hub_catalog_items` (جديد)

```
hub_catalog_items:
  id              PK
  branch_id       FK → branches (CASCADE)
  slug            VARCHAR(120) UNIQUE — للـ URL (مثل "day-package")
  name            VARCHAR(300)
  name_ar         VARCHAR(300) nullable
  name_ru         VARCHAR(300) nullable  ← 4 لغات زي المنيو
  name_it         VARCHAR(300) nullable
  description     TEXT nullable
  description_ar  TEXT nullable
  description_ru  TEXT nullable
  description_it  TEXT nullable
  category        VARCHAR(30) — activity|package|event|beach_service|room_upgrade
  price_per_person NUMERIC(10,2) — السعر للفرد الواحد
  min_persons     INTEGER DEFAULT 1
  max_persons     INTEGER DEFAULT 20
  duration_label  VARCHAR(100) nullable  ← "يوم كامل" / "3 ساعات"
  image_url       VARCHAR(500) nullable  ← الصورة الرئيسية
  gallery_json    TEXT nullable          ← JSON array من URLs (بدون جدول إضافي)
  sort_order      INTEGER DEFAULT 100
  is_published    BOOLEAN DEFAULT FALSE
  requires_date   BOOLEAN DEFAULT TRUE   ← بعض المنتجات تحتاج تاريخ
  created_at / updated_at
```

**لماذا جدول جديد وليس توسيع `hub_offers`؟**
`hub_offers` مصمم للعروض المؤقتة: سعر أصلي/مخفَّض، تاريخ انتهاء، عدد حجوزات محدود.
الكتالوج الدائم له طبيعة مختلفة: منتج ثابت، سعر للفرد، 4 لغات، صور متعددة.
كسر `hub_offers` = كسر HubManagementView الموجود + اختبارات موجودة.

### 3.2 تعديل `HubOnlineBooking` (موجود — تعديل بسيط)

إضافة قيمتين لـ status enum:
```
pending → payment_pending → confirmed
                           → payment_failed → (يمكن إعادة المحاولة)
```

وإضافة أعمدة:
```
catalog_item_id   FK → hub_catalog_items (SET NULL) nullable
paymob_order_id   VARCHAR(100) nullable
paymob_txn_id     VARCHAR(100) nullable
payment_method    VARCHAR(30) nullable  ← card|vodafone_cash
```

### 3.3 `app/resort_os/paymob_gateway.py` (Pure Python — بدون FastAPI/SQLAlchemy)

```python
# نفس نمط food_cost_engine.py / discount_engine.py — pure functions فقط
def authenticate(api_key: str) -> str:           # → auth_token
def create_order(auth_token, amount_cents, ...)  # → paymob_order_id
def get_payment_key(auth_token, order_id, ...)   # → payment_key
def build_hosted_payment_url(payment_key) -> str # → redirect URL
def verify_webhook_hmac(payload, hmac_secret)    # → bool — أهم دالة!
def parse_webhook_payload(raw) -> dict           # → structured result
```

Paymob HMAC verification: المبلغ + order_id + status يُجمعوا كـ string
ويُوقّعوا بـ HMAC-SHA512 بمفتاح سري — هذا هو الحماية من Webhooks مزورة.

### 3.4 API Endpoints الجديدة

#### Public (بدون auth — للموقع)
```
GET  /hub/catalog/public
     ?branch_id=1&category=activity&lang=ar
     → list[CatalogItemPublicRead]
     Cache-Control: public, max-age=300  ← 5 دقائق كافية

GET  /hub/catalog/public/{slug}
     ?branch_id=1
     → CatalogItemPublicRead
```

#### Checkout (بدون auth — للزائر)
```
POST /hub/catalog/{slug}/checkout
     Body: { guest_name, guest_phone, guests_count, requested_date, ... }
     → { booking_id, payment_url }
     # ينشئ HubOnlineBooking (payment_pending) + Paymob order + payment_key
```

#### Webhook (بدون auth — من Paymob فقط)
```
POST /hub/paymob/webhook
     # يتحقق من HMAC → يحدّث booking → يسجّل في Finance
```

#### Staff (مع auth — مدير+)
```
GET    /hub/catalog        → قائمة كاملة بما فيها غير المنشور
POST   /hub/catalog        → إنشاء منتج
PATCH  /hub/catalog/{id}   → تعديل
DELETE /hub/catalog/{id}   → حذف (لو مفيش حجوزات)
POST   /hub/catalog/{id}/image → رفع صورة (نفس نمط DiningItemImage)
```

### 3.5 Finance Integration

عند تأكيد Webhook من Paymob:
```python
# في hub/services.py — confirm_payment_booking()
booking.status = 'confirmed'
booking.paymob_txn_id = txn_id

# تسجيل الدفع في Finance — نفس نمط beach/services.py create_direct_payment
payment = Payment(
    branch_id=booking.branch_id,
    amount=booking.total_amount,
    currency='EGP',
    payment_method='card',  # أو vodafone_cash
    ref_order_id=booking.id,
    # لا folio_id — نفس نمط POS direct payment
)
db.add(payment)
```

### 3.6 واجهة الإدارة — Staff App

في `HubManagementView.vue` — تاب خامس "الكتالوج" بجانب:
bookings | offers | pages | blog | **catalog**

الـ tab يحتوي:
- جدول المنتجات (اسم / النوع / السعر / حالة النشر / إجراءات)
- زر "إضافة منتج" → modal بـ 4 تبويبات (عربي / إنجليزي / روسي / إيطالي)
- toggle نشر/إخفاء في كل صف بضغطة واحدة
- رفع صورة مباشر

### 3.7 موقع التسويق — التغييرات

**`/activities` و `/packages`:**
- بدل i18n ثابت → `GET /hub/catalog/public?category=activity`
- لو الـ API رجّع قائمة فاضية (لم يُنشر أي منتج) → fallback للمحتوى الثابت الحالي
- السعر يظهر فقط لو `PUBLIC_TRUTH.publish.prices === true` (يتحكم فيه Mohamed)

**فلوس الـ Checkout:**
```
كارت المنتج → زر "احجز الآن"
            → modal: اسم + تليفون + تاريخ + عدد أشخاص
            → POST /hub/catalog/{slug}/checkout
            → redirect إلى Paymob hosted page
            → بعد الدفع: redirect إلى /booking/success?ref={public_ref}
            → صفحة نجاح تعرض رقم الحجز ورسالة "سيتواصل معك الفريق"
```

---

## 4. الـ Migration

```
migration: hub_b1_catalog_and_paymob
parent: a3f9c1d2e4b5 (الـ head الحالي)

1. CREATE TABLE hub_catalog_items (...)
2. ALTER TABLE hub_online_bookings
   ADD COLUMN catalog_item_id INTEGER REFERENCES hub_catalog_items(id) ON DELETE SET NULL,
   ADD COLUMN paymob_order_id VARCHAR(100),
   ADD COLUMN paymob_txn_id   VARCHAR(100),
   ADD COLUMN payment_method  VARCHAR(30)
   -- status: القيم الجديدة (payment_pending/payment_failed) متوافقة backward
   -- لأن العمود VARCHAR — لا يحتاج ALTER TYPE
3. CREATE INDEX ix_hub_catalog_items_branch_category ON hub_catalog_items (branch_id, category)
4. CREATE INDEX ix_hub_catalog_items_slug ON hub_catalog_items (slug)
5. CREATE INDEX ix_hub_online_bookings_paymob ON hub_online_bookings (paymob_order_id)
   WHERE paymob_order_id IS NOT NULL
```

**downgrade آمن:** DROP INDEX + DROP COLUMN + DROP TABLE — لا بيانات تُفقد.

---

## 5. متغيرات البيئة المطلوبة

```env
# backend/.env.prod — يضيفها Mohamed قبل النشر
PAYMOB_API_KEY=<من Paymob dashboard>
PAYMOB_CARD_INTEGRATION_ID=<من Paymob dashboard>
PAYMOB_VODAFONE_INTEGRATION_ID=<من Paymob dashboard>
PAYMOB_HMAC_SECRET=<من Paymob dashboard — لـ webhook verification>
PAYMOB_IFRAME_ID=<iframe ID للـ hosted payment page>
```

**تسجيل في `app/core/config.py` — Settings:**
```python
PAYMOB_API_KEY:                    str = ""
PAYMOB_CARD_INTEGRATION_ID:        str = ""
PAYMOB_VODAFONE_INTEGRATION_ID:    str = ""
PAYMOB_HMAC_SECRET:                str = ""
PAYMOB_IFRAME_ID:                  str = ""
```
كلها optional من غير validator — لو فاضية → checkout endpoint يرجّع 503
`payment_not_configured` بدل أي crash.

---

## 6. الـ Invariants الصارمة

### المال والبيانات
- `price_per_person` × `guests_count` = `total_amount` — يُحسب server-side دائمًا، لا نثق بـ `total_amount` من الـ client.
- الدفع يُسجَّل في Finance فقط بعد HMAC verification ناجح من Paymob — لا تأكيد بدون verification.
- `paymob_order_id` unique index — لا تسجيل دفع مكرر لو Webhook جاء مرتين (idempotency).
- الحجز لا ينتقل من `payment_pending` إلا بـ webhook — لا يغيّر أي موظف status إلى confirmed يدويًا لحجز Paymob.

### الأمان
- Webhook endpoint: HMAC verification أول خطوة، لو فاشل → 400 بدون logging للـ payload (حماية من log injection).
- `branch_id` في الـ checkout يُشتق من `slug` — لا نثق به من الـ client.
- `guest_name` / `guest_phone` في `hub_online_bookings` مشفرة بـ `EncryptedString` بالفعل ✅.
- Rate limit على `/hub/catalog/{slug}/checkout` — نفس آلية hub/contact.

### التوافق
- `hub_offers` والـ `HubManagementView` الحاليين لا يتغيران.
- كل endpoints الجديدة في نفس `hub/api/router.py` — لا ملف router جديد.
- الكتالوج الفاضي (لم يُنشر أي منتج) لا يكسر الموقع — fallback للمحتوى الثابت.

---

## 7. الملفات المتوقعة

### Backend (جديدة أو معدّلة)
```
backend/alembic/versions/<hash>_hub_b1_catalog_and_paymob.py  ← جديد
backend/app/resort_os/paymob_gateway.py                        ← جديد (pure Python)
backend/app/core/config.py                                     ← إضافة Paymob fields
backend/app/modules/hub/models.py                              ← HubCatalogItem جديد + HubOnlineBooking أعمدة
backend/app/modules/hub/schemas.py                             ← CatalogItemCreate/Read/PublicRead + checkout schemas
backend/app/modules/hub/crud.py                                ← list/get/create/update catalog
backend/app/modules/hub/services.py                            ← checkout_catalog_item + confirm_payment_booking
backend/app/modules/hub/api/router.py                          ← endpoints الجديدة
backend/tests/test_api/test_hub_catalog.py                     ← جديد (اختبارات شاملة)
```

### Frontend — Staff App (معدّل)
```
frontend/apps/el-kheima/src/views/admin/HubManagementView.vue  ← تاب catalog
frontend/packages/core/src/api/endpoints.ts                    ← hub.catalog endpoints
frontend/packages/core/src/i18n/locales/ar.json                ← مفاتيح hub.catalog
frontend/packages/core/src/i18n/locales/en.json                ← نفس المفاتيح
```

### Frontend — Marketing Website (معدّل)
```
src/apps/public/Activities.vue   ← يجيب من API + fallback
src/apps/public/Packages.vue     ← يجيب من API + fallback
src/composables/useCatalog.ts    ← جديد — جلب + caching
src/config/publicTruth.ts        ← prices: false → true عند Approval B
src/apps/public/BookingSuccess.vue ← جديد — صفحة نجاح الدفع
```

---

## 8. Acceptance Criteria

1. مدير يضيف منتج "باقة نهار كامل" بسعر 500ج، ينشره → يظهر فورًا على الموقع بدون أي تعديل كود.
2. مدير يوقف المنتج → يختفي من الموقع فورًا.
3. زائر يضغط "احجز" على باقة بسعر 500ج × 2 شخص → يُعاد توجيهه لـ Paymob بمبلغ 1000ج.
4. Paymob يبعت Webhook ناجح → `HubOnlineBooking.status = confirmed` + `Payment` record في Finance.
5. Paymob يبعت Webhook مكرر لنفس الـ order → لا duplciate payment (idempotency).
6. Webhook بـ HMAC خاطئ → 400، لا تغيير في DB.
7. موقع بدون أي منتج منشور → يعرض المحتوى الثابت من i18n بدون error.
8. `price_per_person` × 3 = `total_amount` في الـ booking — دايمًا server-side.
9. `guest_phone` في DB مشفر — لا يظهر plaintext في SQL dump.
10. `checkout` بـ `guests_count` = 0 أو `guests_count` = 100 → 422.

---

## 9. خطة الاختبارات

### Backend
```python
class TestHubCatalog:
    test_create_catalog_item_manager_only()
    test_public_list_returns_published_only()
    test_public_list_by_category()
    test_checkout_creates_booking_and_returns_payment_url()
    test_checkout_calculates_total_server_side()
    test_checkout_unpublished_item_returns_404()
    test_webhook_valid_hmac_confirms_booking_and_records_payment()
    test_webhook_invalid_hmac_returns_400()
    test_webhook_duplicate_order_id_is_idempotent()
    test_checkout_rate_limit()
    test_paymob_not_configured_returns_503()
    test_branch_id_derived_from_slug_not_client()
```

### Frontend
- TypeScript type-check نظيف
- i18n validation نظيف (لا مفاتيح مفقودة)
- Activities/Packages تعرض fallback لو API فاشل

---

## 10. ترتيب التنفيذ (Phase by Phase)

| المرحلة | المحتوى | الأولوية |
|---|---|---|
| **Phase 1** | Migration + `HubCatalogItem` model + schemas + CRUD + public list endpoint | أولاً |
| **Phase 2** | Paymob gateway (pure Python) + checkout endpoint + webhook | ثانياً |
| **Phase 3** | Staff app — تاب الكتالوج في HubManagementView | ثالثاً |
| **Phase 4** | Marketing website — Activities/Packages ديناميكية + صفحة نجاح | رابعاً |
| **Phase 5** | Tests شاملة + validation contract + Approval B decision | خامساً |

كل مرحلة = diff مستقل قابل للمراجعة. لا تبدأ مرحلة قبل اكتمال السابقة.

---

## 11. Stop Conditions

توقف وانتظر Mohamed عند:
- أسعار المنتجات الفعلية (ما في البرنامج لا أسعار حقيقية بعد)
- `PAYMOB_API_KEY` والـ credentials الحقيقية
- هل تفعيل فودافون كاش مطلوب من البداية أم فيزا/ماستر أولاً؟
- هل صفحة `/booking/success` تُرسل إيميل تأكيد للزائر؟

---

## 12. متطلبات التسليم

كل مرحلة تتضمن:
- ملخص الـ diff والملفات المهمة
- نتائج `pytest` + `alembic heads` + `type-check`
- أثر المالية والأمان
- المخاطر المتبقية
- لا commit أو push بدون إذن صريح من Mohamed
