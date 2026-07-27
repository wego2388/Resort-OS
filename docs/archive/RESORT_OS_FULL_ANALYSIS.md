# 📋 توثيق شامل — Resort OS + تحليل النظام القديم Trucker ERP

> **تاريخ التوثيق:** 2026-07-01  
> **الكاتب:** Kiro AI — تحليل مباشر من الكود والملفات  
> **الهدف:** مرجع كامل للمشروع الجديد + دروس مستفادة من النظام القديم

---

## الفهرس

1. [نظرة عامة على resort-os](#1-نظرة-عامة)
2. [Tech Stack التفصيلي](#2-tech-stack)
3. [المعمارية الكاملة](#3-المعمارية)
4. [الـ 14 Module — تفاصيل كل وحدة](#4-الـ-14-module)
5. [Auth & Security Chain](#5-auth--security)
6. [قاعدة البيانات والمعاملات](#6-قاعدة-البيانات)
7. [Celery Background Tasks](#7-celery)
8. [Frontend — 7 تطبيقات](#8-frontend)
9. [تغطية الاختبارات](#9-اختبارات)
10. [نقاط الضعف والمخاطر](#10-نقاط-الضعف)
11. [النظام القديم Trucker ERP — تحليل شامل](#11-trucker-erp-القديم)
12. [مقارنة القديم بالجديد](#12-مقارنة)
13. [ميزات ناقصة في resort-os](#13-ميزات-ناقصة)
14. [خارطة الطريق الموصى بها](#14-خارطة-الطريق)

---

## 1. نظرة عامة

**Resort OS** نظام ERP/PMS/POS متكامل لإدارة المنتجعات السياحية — مبني خصيصاً لـ **WegoSharm** بشرم الشيخ.

### ما الذي يفعله النظام؟
- **PMS** (Property Management System) — إدارة الحجوزات والغرف والفنادق
- **POS** (Point of Sale) — نقطة بيع المطعم والكافيه مع شاشة مطبخ KDS
- **ERP** كامل — مالية، موارد بشرية، مخزن، صيانة، CRM، تايم شير، شاطئ، إيجارات
- **Digital Hub** — موقع عام وبوابة الضيوف QR
- **تكامل ETA** — فواتير إلكترونية مع الضرائب المصرية

### الفريق والبيئة
- المشروع قيد التطوير النشط (آخر تحديث: Jun 2026)
- يشارك **wego-core** مع 5 مشاريع أخرى في نفس الجهاز
- يعمل كاملاً محلياً بـ Docker


---

## 2. Tech Stack

### Backend
| التقنية | الإصدار | الاستخدام |
|---------|---------|-----------|
| Python | 3.12 | لغة البرمجة الأساسية |
| FastAPI | 0.115.6 | ASGI web framework |
| SQLAlchemy | 2.0.36 | ORM |
| Alembic | 1.14.0 | Database migrations |
| PostgreSQL | Docker (latest) | قاعدة البيانات الرئيسية — port 5436 |
| Redis | Docker (latest) | Cache + Rate Limiting + Celery broker — port 6381 |
| Celery | 5.4.0 | Background tasks + scheduled jobs |
| Pydantic v2 | 2.10.4 | Data validation |
| python-jose | 3.3.0 | JWT tokens |
| cryptography | 44.0.0 | Fernet encryption للبيانات الحساسة |
| uvicorn | 0.32.1 | ASGI server |
| httpx | 0.28.1 | HTTP client |
| loguru | 0.7.3 | Logging |
| sentry-sdk | 2.19.2 | Error monitoring |
| wego-core | 1.0.0 (editable) | Shared auth/cache/payments/notifications |

### Frontend
| التقنية | الإصدار | الاستخدام |
|---------|---------|-----------|
| Vue 3 | 3.5.39 | JavaScript framework |
| TypeScript | 5.9.3 | Type safety |
| Vite | latest | Build tool |
| pnpm | latest | Package manager (monorepo) |
| Pinia | latest | State management |
| Vue Router | 4.6.4 | Routing |
| vite-plugin-pwa | 7.4.1 (workbox) | PWA + Service Worker |

### Infrastructure
| الخدمة | Port | الملاحظة |
|--------|------|-----------|
| Backend API | 8005 | FastAPI |
| POS App | 3001 | Vue 3 |
| KDS App | 3002 | Vue 3 |
| OPS App | 3003 | Vue 3 |
| Admin App | 3004 | Vue 3 |
| QR App | 3005 | Vue 3 |
| Portal App | 3006 | Vue 3 |
| Public App | 3007 | Vue 3 |
| PostgreSQL | 5436 | Docker |
| Redis | 6381 | Docker |


---

## 3. المعمارية

### Backend Architecture
```
backend/
├── app/
│   ├── main.py                 ← App factory + middleware + lifespan
│   ├── core/
│   │   ├── config.py           ← Settings (inherits WegoSettings)
│   │   ├── database.py         ← SQLAlchemy engine + get_db (re-export من wego_core)
│   │   ├── deps.py             ← Auth chain + role levels + rate_limit_dep
│   │   ├── encryption.py       ← EncryptedString TypeDecorator (Fernet)
│   │   ├── module_loader.py    ← Module registry + toggle system
│   │   └── rate_limit.py       ← IP-based middleware
│   ├── modules/
│   │   └── <name>/             ← 14 module، كل واحد بنفس الهيكل:
│   │       ├── models.py       ← SQLAlchemy ORM models
│   │       ├── schemas.py      ← Pydantic v2 schemas
│   │       ├── crud.py         ← DB operations ONLY (لا HTTPException)
│   │       ├── services.py     ← Business logic (يرمي ValueError → 400)
│   │       └── api/router.py   ← HTTP layer (يترجم الأخطاء)
│   ├── resort_os/              ← Pure domain engines (لا HTTP dependencies)
│   │   ├── discount_engine.py  ← حساب الخصومات والعروض
│   │   ├── folio_engine.py     ← حساب فواتير الضيوف
│   │   ├── beach_engine.py     ← إدارة مساحات الشاطئ
│   │   ├── hr_engine.py        ← حساب الرواتب والإجازات
│   │   ├── timeshare_engine.py ← عقود التايم شير والدفعات
│   │   └── report_builder.py   ← PDF/Excel reports
│   ├── tasks/                  ← Celery tasks (مسجلة في celery_app.py)
│   │   ├── analytics_tasks.py
│   │   ├── beach_tasks.py
│   │   ├── crm_tasks.py
│   │   ├── finance_tasks.py
│   │   ├── hr_tasks.py
│   │   ├── hub_tasks.py
│   │   ├── inventory_tasks.py
│   │   ├── leasing_tasks.py
│   │   ├── maintenance_tasks.py
│   │   ├── pms_tasks.py
│   │   └── timeshare_tasks.py
│   └── seed.py                 ← Idempotent seed data
├── alembic/
│   └── versions/               ← 12 migration file
└── tests/
    ├── test_api/               ← 17 test file (HTTP layer — غير مستخدمة)
    ├── test_engines/           ← 7 test file (domain engines)
    ├── test_modules/           ← 1 test file (ETA service)
    └── test_tasks/             ← 1 test file (analytics tasks)
```

### Module Toggle System (الفكرة المميزة)
```
Startup: كل الـ 14 router يتسجل دايماً
         ↓
Request يوصل → require_module("beach") dependency
         ↓
Redis cache (TTL=60s) → هل module مفعّل؟
         ↓          ↓
       نعم         لا  → 403 Module Disabled
         ↓
      Execute endpoint

Toggle: PATCH /api/v1/core/modules/{key} 
        → DB update + Redis cache invalidation
        → فعّال فوراً بدون restart
```

### Frontend Architecture
```
frontend/
├── packages/
│   ├── core/                   ← @resort-os/core
│   │   ├── api/client.ts       ← Axios instance + interceptors
│   │   ├── api/endpoints.ts    ← كل الـ API endpoints
│   │   ├── stores/auth.ts      ← Pinia auth store
│   │   ├── stores/modules.ts   ← Module states store
│   │   └── composables/
│   │       ├── useWebSocket.ts ← Real-time updates
│   │       └── useOfflineQueue.ts ← Offline POS queue (IndexedDB)
│   └── ui/                     ← @resort-os/ui
│       ├── components/         ← Button, Card, Input, Modal, Badge, Spinner, Toast
│       └── views/LoginView.vue
└── apps/ (7 تطبيقات — كل واحد Vite app مستقل)
    ├── pos/    ← نقطة البيع + Offline POS + PWA
    ├── kds/    ← Kitchen Display System + PWA  
    ├── ops/    ← Operations dashboard + PWA
    ├── admin/  ← Admin panel (module management, users, reports)
    ├── qr/     ← Guest QR portal
    ├── portal/ ← Employee portal
    └── public/ ← Public website
```


---

## 4. الـ 14 Module — تفاصيل كل وحدة

| Module | Arabic | Always On | Dependencies | Default |
|--------|--------|-----------|--------------|---------|
| core | النظام الأساسي | ✅ | — | دائماً |
| finance | المالية والمحاسبة | ✅ | — | دائماً |
| inventory | المخازن | ✅ | — | دائماً |
| hr | الموارد البشرية | ✅ | — | دائماً |
| maintenance | الصيانة والأصول | ❌ | core | مفعّل |
| analytics | التحليلات | ❌ | core | مفعّل |
| restaurant | المطعم + POS | ❌ | inventory | مفعّل |
| cafe | الكافيهات | ❌ | inventory | معطّل |
| pms | إدارة الفندق | ❌ | finance | معطّل |
| timeshare | التايم شير | ❌ | pms | معطّل |
| beach | الشاطئ | ❌ | finance | معطّل |
| crm | إدارة العملاء | ❌ | core | معطّل |
| hub | المنصة الرقمية | ❌ | core | معطّل |
| leasing | الإيجارات | ❌ | finance | معطّل |

### Core Module
- إدارة المستخدمين والأدوار (roles & permissions)
- إدارة الفروع (branches)
- إدارة الإعدادات العامة (settings)
- Module toggle system (تشغيل/إيقاف modules)
- Audit log للعمليات الحساسة

### Finance Module
- دفتر اليومية (Journal Entries) — شجرة حسابات كاملة
- الفواتير والمدفوعات
- الخزائن (Safes) وإدارة النقدية
- مراكز التكلفة (Cost Centers)
- **E-Invoice ETA** — تكامل مع بوابة الضرائب المصرية
- كشف حساب وميزان المراجعة

### HR Module
- ملفات الموظفين (بيانات شخصية، وثائق)
- الحضور والانصراف
- إدارة المناوبات (Shifts)
- الرواتب والاستحقاقات والخصومات
- أنواع الإجازات (8 أنواع في seed)
- طلبات الإجازات
- التأمينات الاجتماعية (config في seed)
- شرائح ضريبة الدخل 2024

### Inventory Module
- إدارة المنتجات (categories, units, variants)
- سندات الإضافة والصرف والتحويل
- مستويات المخزن وتنبيهات الحد الأدنى
- تكامل مع المطعم والكافيه

### Restaurant Module
- إدارة القائمة (menu items, categories, extras, groups)
- طاولات وغرف الطعام
- الطلبات (dine-in, takeaway, delivery)
- نقطة بيع متكاملة (POS Front End)
- **Offline POS** — عبر IndexedDB + sync
- شاشة المطبخ (KDS)
- Void/Cancel orders
- تقارير نهاية الشيفت

### PMS Module
- إدارة الغرف والأنواع والأسعار
- حجوزات الفندق مع **Concurrency-safe locking** (SELECT FOR UPDATE NOWAIT)
- Check-in / Check-out
- Folio الضيف (تجميع الفواتير)
- Walk-in guests

### Timeshare Module
- عقود التايم شير (المالك، الوحدة، السنوات)
- جداول الدفع والأقساط
- المبادلات (exchanges) بين المالكين
- تتبع الحالة (نشط، منتهٍ، موقوف)
- تقارير العقود

### Beach Module
- المساحات والكراسي والمظلات
- حجوزات الشاطئ اليومية
- خدمات الشاطئ (extras)
- تقارير الإيرادات

### CRM Module
- قاعدة العملاء (Leads, Customers, Guest Profiles)
- الأنشطة والمتابعات
- الحملات التسويقية
- تقارير المبيعات

### Analytics Module
- لوحة معلومات KPIs
- استطلاعات رضا الضيوف (Guest Surveys)
- تقارير الإيرادات اليومية/الشهرية/السنوية
- تحليل الأداء حسب الوحدة

### Hub Module (Digital Hub)
- الموقع العام للمنتجع
- مدونة وأخبار
- نموذج تواصل (مع rate limiting)
- إدارة المحتوى

### Maintenance Module
- أوامر العمل (Work Orders)
- الأصول الثابتة وجداول الصيانة الدورية
- تتبع حالة الأصول
- تقارير الصيانة

### Leasing Module
- عقود الإيجار (موقع، مستأجر، مدة، سعر)
- متابعة الدفعات
- تحذيرات انتهاء العقود
- تشفير بيانات المستأجر (national_id)

### Cafe Module
- مشابه للـ restaurant لكن لقوائم الكافيه
- معطّل افتراضياً ويحتاج تفعيل


---

## 5. Auth & Security

### Auth Chain
```
JWT Token
    ↓
get_current_user
  → JWT decode
  → token_blacklist check (Redis)
  → token revocation check (iat vs revoke timestamp)
  → DB user lookup (by email — مش username)
    ↓
get_current_active_user
  → is_active check
  → Mandatory 2FA gate (super_admin + accountant)
    ↓
Role-based gates:
  get_waiter_user    → level ≥ 30
  get_cashier_user   → level ≥ 40
  get_manager_user   → level ≥ 60
  get_admin_user     → level ≥ 80
  get_super_admin_user → level ≥ 100
```

### Role Levels (محسوبة runtime من ROLE_LEVELS dict — مش column في DB)
```python
ROLE_LEVELS = {
    "waiter": 30,
    "cashier": 40,
    "manager": 60,
    "admin": 80,
    "accountant": 80,
    "super_admin": 100,
}
```

### Mandatory 2FA
- مطلوب لـ: `super_admin` و `accountant`
- أي endpoint غير `/api/v1/auth/*` يرجع **403 2FA_REQUIRED**
- Flow: login → POST /auth/2fa/setup → scan QR → POST /auth/2fa/enable

### Token Revocation
- `revoke_user_tokens(user_id)` يحط `user_revoked:{id}` في Redis
- TTL = REFRESH_TOKEN_EXPIRE_DAYS
- أي token بـ `iat` قبل وقت الـ revoke يُرفض بـ 401
- يُستدعى تلقائياً عند تغيير role أو is_active

### Rate Limiting
**IP-based (Middleware):**
- `/auth/login` + `/auth/register`: 5 requests / 300s
- `/hub/contact` + `/hub/blog/posts`: 30 requests / 60s

**Resource-based (Dependency):**
- `/finance/eta/invoices`: 100 requests / 60s

### Field Encryption (Fernet)
جداول فيها تشفير تلقائي لـ `national_id`:
- `employees.national_id`
- `bookings.guest_national_id`
- `crm_customers.national_id`
- `guest_profiles.national_id`
- `lease_contracts.tenant_national_id`
- `timeshare_contracts.customer_national_id`

### Security Headers
- `SecurityHeadersMiddleware` من wego-core (X-Frame-Options, CSP, etc.)
- `CorrelationMiddleware` — correlation ID per request
- CORS مُقيّد بقائمة محددة من الـ origins

---

## 6. قاعدة البيانات

### الـ Migrations
```
47f5f348_initial_core_tables      ← الجداول الأساسية
b7e2d415_pms_beach                ← PMS + Beach
a3f8c291_finance_hr_restaurant    ← Finance + HR + Restaurant
c9f1a852_new_models               ← CRM + Leasing + Timeshare
e2f4a610_crm_lead_guestprofile    ← CRM Guest Profiles
d1e3f920_finance_check_cost_center ← Finance checks + cost centers
f3b5c740_hub_blog_contact         ← Hub module
af9285101fa9_missing_module_tables ← جداول ناقصة
5c181f7389c6_merge_finance_crm    ← Merge heads
07f92639806e_orders_client_local_id ← Offline POS idempotency
12f21e50c5f0_eta_invoices_table   ← ETA integration
347cbfa7a11d_encrypt_national_id  ← Fernet encryption migration
67a5a4cf1db5_timeshare_expanded   ← Timeshare contract fields
```

### Seed Data (app/seed.py — Idempotent)
- super_admin user: `admin@resortos.local` / `Admin@123456`
- Default branch
- Module states (الـ 14 module بـ default values)
- Social insurance config
- Tax brackets 2024
- General settings
- 8 leave types
- Chart of accounts (13 حساب أساسي)

### Concurrency Safety
```python
# حجوزات الغرف — SELECT FOR UPDATE NOWAIT
# حجزين متزامنين لنفس الغرفة:
# واحد ينجح (201) والتاني يرجع BookingConflictError (409)
crud.lock_room_for_booking(db, room_id)
```

⚠️ لا يعمل على SQLite — يحتاج PostgreSQL


---

## 7. Celery Background Tasks

### الإعداد
- Broker: Redis (`redis://localhost:6381/0`)
- Backend: Redis
- كل ملف في `app/tasks/` **لازم** يُستورد في `celery_app.py`

### قائمة الـ Tasks
| الملف | المحتوى التقريبي |
|-------|-----------------|
| analytics_tasks.py | حساب KPIs اليومية، تجميع إحصائيات |
| beach_tasks.py | تحذيرات حجوزات الشاطئ، تقارير |
| crm_tasks.py | متابعة leads، إرسال reminders |
| finance_tasks.py | تذكيرات دفعات، تسوية حسابات |
| hr_tasks.py | حساب رواتب، تنبيهات انتهاء عقود |
| hub_tasks.py | نشر محتوى، إرسال emails |
| inventory_tasks.py | تنبيهات نقص المخزن |
| leasing_tasks.py | تذكيرات تجديد عقود الإيجار |
| maintenance_tasks.py | جدولة صيانة دورية |
| pms_tasks.py | تقارير الإشغال، check-out تلقائي |
| timeshare_tasks.py | تذكيرات الأقساط، تقارير العقود |

---

## 8. Frontend — 7 تطبيقات

### @resort-os/core (Shared Package)
```typescript
// api/client.ts — Axios instance
// api/endpoints.ts — كل API calls

// stores/auth.ts (Pinia)
// stores/modules.ts — enabled modules cache

// composables/useWebSocket.ts — real-time WebSocket
// composables/useOfflineQueue.ts — IndexedDB offline queue
```

### useOfflineQueue — Offline POS
```typescript
// عند فقد الاتصال:
// 1. الطلب يحفظ في IndexedDB
// 2. عند عودة online: FIFO sync
// 3. poll كل 30 ثانية كـ fallback
// 4. Backend: POST /api/v1/restaurant/orders/sync
//    يقبل: {local_id, ...order} — idempotent بـ client_local_id
//    يرجع: {order_id, status: fulfilled|partial|rejected, ...}
```

### PWA Apps
التطبيقات التالية فيها Service Worker + App Shell caching:
- **pos** — نقطة البيع (offline-first)
- **kds** — شاشة المطبخ
- **ops** — لوحة العمليات

أيقونات في `apps/<app>/public/icon-{192,512}.png`  
PWA manifest يتولّد في build فقط (مش dev mode)

---

## 9. اختبارات

### الوضع الحالي
```
441 test — كلها بتعدي ✅ في 3.72 ثانية
Coverage الإجمالي: 63%
```

### تفصيل التغطية
| الجزء | Coverage | الملاحظة |
|-------|---------|-----------|
| Domain Engines (resort_os/) | 89%–100% | ممتاز |
| Models + Schemas | ~100% | ممتاز |
| Core modules (discount, hr, folio) | 89–99% | جيد جداً |
| Services (business logic) | 31–75% | متوسط |
| API Routers (HTTP layer) | **0%** | فجوة كبيرة |
| Celery Tasks | 16–26% | ضعيف |
| seed.py | 0% | لم يُختبر |
| report_builder.py | 0% | لم يُختبر |

### طريقة الاختبار الحالية
```python
# كل الـ 441 test بتنادي services مباشرة بـ SQLite in-memory
# مثال:
def test_create_booking(db):
    result = services.create_booking(db, booking_data)
    assert result.status == "confirmed"
    
# الـ HTTP fixtures موجودة في conftest.py لكن:
# 1. مش مستخدمة في أي test
# 2. فيها bug (token مش متوافق مع email-based lookup)
```

### تشغيل الاختبارات
```bash
cd backend && source .venv/bin/activate
pytest tests/ -q                    # كل الاختبارات
pytest tests/ --cov=app --cov-report=term-missing -q  # مع coverage
make test                            # من root
make test-cov                        # من root مع coverage
```


---

## 10. نقاط الضعف والمخاطر

### 🔴 عالية الأولوية

**1. HTTP Layer Coverage = 0%**
- جميع `api/router.py` files غير مختبرة
- الـ HTTP behavior (status codes, error handling, auth gates) غير مضمونة
- التوثيق نفسه يقول "تأكد منه بـ curl" — مش acceptable في production

**2. Celery Tasks Coverage ضعيف (16–26%)**
- tasks زي `timeshare_tasks`, `crm_tasks` coverage أقل من 20%
- فشلها في production صعب اكتشافه

**3. timeshare/services.py — 31% فقط**
- نظام التايم شير business-critical وفيه منطق مالي معقد
- الـ timeshare_engine.py رغم 91% coverage، لكن service layer ضعيف

**4. Timeshare + Beach + CRM معطّلة افتراضياً**
- الـ models والـ schemas موجودة لكن services غير مكتملة الاختبار
- لو فُعّلت في production ممكن تظهر bugs

### 🟡 متوسطة الأولوية

**5. wego-core Coupling**
- المشروع يعتمد كلياً على `wego-core` كـ editable install
- أي تغيير في wego-core ممكن يكسر resort-os
- لا يوجد version pinning أو compatibility tests

**6. Docker TLS Issue (موثّق)**
- image pulls بتفشل بـ TLS mismatch على هذه الـ machine
- workaround: `public.ecr.aws/docker/library/<image>:<tag>` ثم `docker tag`
- CI/CD غير موثوق بدون حل دائم

**7. Migration History معقد**
- تاريخياً: 3 migration heads متفرقة + 53 جدول بدون migration
- الوضع اتحل لكن تاريخ الـ migrations غير نظيف
- لو عملت fresh install على server جديد ممكن تلاقي مشاكل

**8. report_builder.py = 0% Coverage**
- كود موجود لكن لم يُختبر أبداً
- يولّد PDF/Excel reports المهمة

### 🟢 ملاحظات تحسين

**9. HTTP Fixtures معطّلة**
- `conftest.py` فيه `client` و`super_admin_headers` لكن مش شغّالين
- بتصليحهم تقدر ترفع coverage بـ 20%+ في يوم واحد

**10. apps/ directory مش مكتشف**
- في `pnpm-workspace.yaml` بيشير لـ `apps/` لكن محتواه مش موثّق
- ممكن يكون فيه apps غير مكتملة

---

## 11. النظام القديم Trucker ERP — تحليل شامل

### ما هو Trucker ERP؟
نظام ERP مكتبي (Desktop) مبني بـ **C# / .NET Framework 4.5.2** باستخدام:
- **DevExpress 22.2** — UI Components (من أقوى مكتبات UI في .NET)
- **SQL Server Express** — قاعدة البيانات
- **DevExpress XPO** — ORM
- **CefSharp** — Chromium embedded browser داخل الـ app
- **Dapper** — Micro ORM للـ raw SQL
- **RestSharp** — HTTP client للـ APIs الخارجية
- **Crystal Reports → DevExpress Reports** — التقارير

### التطبيقات المضمّنة
| الملف | الاسم | الوظيفة |
|-------|-------|---------|
| `Trucker ERP.exe` | ERP الرئيسي | النظام الكامل |
| `Trucker_Front.exe` | Trucker Front | واجهة POS الأمامية |
| `POS Front End.exe` | POS Front End | نقطة بيع |
| `Order taker.exe` | Order Taker | تطبيق أخذ الطلبات |
| `Click KDS.exe` | Click KDS | شاشة المطبخ |
| `Click_HR.exe` | Click HR | نظام الموارد البشرية |
| `Trucker_Production.exe` | Production | إدارة الإنتاج |
| `Click_Utility.exe` | Utility | أدوات مساعدة |
| `AutoUpdate.exe` | Auto Update | تحديث تلقائي |
| `Trucker Whatsapp.exe` | WhatsApp | إرسال رسائل واتساب |

### الـ 3 Database Variants
النظام القديم فيه 3 نسخ من قاعدة البيانات:

**1. Trucker (138 جدول) — الأكبر والأشمل**
نظام ERP كامل يغطي:
- محاسبة كاملة (JL_Entries, JLTree, Accounts, Accounts_Movement)
- CRM متكامل (8+ جداول CRM)
- HR شامل (attendance, shifts, salary, holidays, fingerprint)
- مخزن وفواتير
- بصريات (Optical — متخصص)
- E-Invoice (Saudi KSA)
- POS مطعم
- عقود وصيانة سيارات (CC_ tables)
- SmartCard + Delivery

**2. Trade (86 جدول) — للتجارة**
متخصص في:
- بيع وشراء (Sales/Purchase invoices)
- مخزون بالـ serials
- تركيب وصيانة (Maintenance_Sheets)
- مواعيد (Appointments)
- كتب وبيانات (Books_data — مكتبات)
- صيانة سيارات (Cars, Cars_Of_Customers)
- بصريات (Optics_Sheet)
- تصنيع (Manufacturing_order)
- شحن (Shipping_Companies, Shiping_Bond)

**3. Dinner (70 جدول) — للمطاعم**
متخصص في:
- مطعم فقط (Tables, Rooms, Kitchen)
- توصيل (DeliveryBoys, Otlob_service)
- إنتاج (FinshGoodStorages, RawMaterial)
- عضوية (MemberShips)
- قوائم طعام متعددة الأحجام (R_mealsizes)
- Void data

### الميزات الفريدة في النظام القديم

**1. نظام الصلاحيات المتقدم**
```sql
UsersScreenAccessDetails   ← صلاحية لكل شاشة بشكل منفصل
UsersSettingsProfiles      ← profiles للإعدادات
UsersSettingsProfileProperties
```

**2. نظام تزامن متعدد الفروع (Sync)**
```sql
TBL_Sync_report_settings   ← إعدادات التزامن
synctst                     ← اختبار التزامن
PC_data                     ← بيانات الجهاز (last login, last update, current version)
Microsoft.Synchronization.* ← مكتبة SQL Server Sync
```

**3. E-Invoice متعدد الدول**
```sql
ksa_E_invoice_header/details  ← E-Invoice السعودية
tbl_general_e_invoice         ← E-Invoice عام (مصر؟)
```

**4. نظام WhatsApp متكامل**
```sql
tbl_whatsapp_tasks            ← قائمة انتظار رسائل الواتساب
SMS_Log, SMS_templates         ← SMS backup
```

**5. نظام الشيكات والدفعات المؤجلة**
```sql
TBL_Chequ_List               ← قائمة الشيكات
TBL_Chequ_movement           ← حركات الشيكات
PaymentWarning               ← تحذيرات الدفع
PaymentWarning_payed         ← الدفعات المسددة
Installments_Contracts/Details ← عقود التقسيط
```

**6. نقاط الولاء (Loyalty Points)**
```sql
Points_Managment             ← إدارة النقاط
tbl_smartcard_loaded         ← البطاقات الذكية
tbl_discounts_cards          ← بطاقات الخصومات
MemberShips_List             ← العضويات
```

**7. Sticky Notes داخل النظام**
```sql
sticky_notes                 ← ملاحظات داخلية للمستخدمين
```

**8. Calendar Table**
```sql
CalendarTable                ← جدول التقويم الكامل مع حسابات يوليانية
-- يستخدم للتقارير الزمنية السريعة
```

**9. نظام القوالب والطباعة**
```sql
tbl_templates                ← قوالب المستندات
TBL_Printers                 ← إدارة الطابعات
TBL_Receipt_Tree             ← شجرة الإيصالات
```

**10. نظام الإنتاج والتصنيع**
```sql
Manfuct_Simple               ← تصنيع مبسّط
Manufacturing_order/Details  ← أوامر الإنتاج
TBL_Inventory_Finishgood     ← مخزن المنتج النهائي
RawMaterialMovement          ← حركة المواد الخام
```


---

## 12. مقارنة القديم (Trucker) بالجديد (Resort OS)

### جدول المقارنة الشامل

| الميزة | Trucker ERP (قديم) | Resort OS (جديد) | الفجوة |
|--------|-------------------|-----------------|--------|
| **Platform** | Windows Desktop (.NET) | Web (Browser/PWA) | — |
| **Database** | SQL Server Express | PostgreSQL | — |
| **UI** | DevExpress WinForms | Vue 3 + TypeScript | — |
| **Multi-branch** | ✅ مع sync كامل | ✅ لكن بدون offline sync للـ branches | ⚠️ |
| **POS** | ✅ كامل مع offline | ✅ مع offline قيد التطوير | ✅ |
| **KDS** | ✅ Click KDS.exe | ✅ kds app | ✅ |
| **Order Taker** | ✅ تطبيق منفصل | ❌ غير موجود | ❌ |
| **HR كامل** | ✅ كامل + fingerprint | ✅ لكن بدون fingerprint | ⚠️ |
| **محاسبة** | ✅ دفتر يومية + ميزان | ✅ نفس المستوى | ✅ |
| **E-Invoice** | ✅ KSA + مصر | ✅ مصر (ETA) | ✅ |
| **WhatsApp** | ✅ تطبيق مستقل | ❌ مذكور فقط (config فارغ) | ❌ |
| **SMS** | ✅ قوالب + log | ❌ config فارغ | ❌ |
| **CRM** | ✅ كامل (leads, activities) | ✅ معطّل افتراضياً | ⚠️ |
| **نقاط الولاء** | ✅ Points + SmartCard | ❌ غير موجود | ❌ |
| **بطاقات الخصومات** | ✅ | ❌ | ❌ |
| **الشيكات** | ✅ قائمة + حركات | ❌ غير موجود | ❌ |
| **التقسيط** | ✅ عقود تقسيط | ❌ غير موجود | ❌ |
| **تزامن متعدد الفروع** | ✅ Microsoft Sync | ❌ | ❌ |
| **صلاحيات per-screen** | ✅ UsersScreenAccessDetails | ❌ role-based فقط | ❌ |
| **PMS (فندق)** | ❌ | ✅ | ✅ |
| **Timeshare** | ❌ | ✅ | ✅ |
| **Beach Management** | ❌ | ✅ | ✅ |
| **Leasing (إيجارات)** | ✅ tbl_contracts | ✅ | ✅ |
| **Digital Hub** | ❌ | ✅ | ✅ |
| **PWA / Mobile** | ❌ Windows only | ✅ | ✅ |
| **REST API** | ❌ | ✅ كامل | ✅ |
| **2FA** | ❌ | ✅ | ✅ |
| **Field Encryption** | ❌ | ✅ Fernet | ✅ |
| **Analytics Dashboard** | ✅ تقارير DevExpress | ✅ لكن محدود | ⚠️ |
| **Sticky Notes** | ✅ | ❌ | ❌ |
| **Auto Update** | ✅ | N/A (web) | — |
| **Barcode/QR Labels** | ✅ | ✅ (qr app) | ✅ |
| **Production/Mfg** | ✅ | ❌ | ❌ |
| **Optical (بصريات)** | ✅ متخصص | ❌ | N/A |
| **Car Maintenance** | ✅ | ❌ | N/A |
| **Calendar Table** | ✅ optimized | ❌ | ⚠️ |

---

## 13. ميزات ناقصة في resort-os

### 🔴 ناقصة وضرورية (لمقارعة الـ Trucker)

**1. Order Taker App**
- تطبيق الويتر على التابلت لأخذ الطلبات
- في Trucker: `Order taker.exe`
- في resort-os: يحتاج تطبيق Vue 3 جديد (مثل kds) أو page في portal

**2. نقاط الولاء (Loyalty Program)**
```
Tables: loyalty_programs, customer_points, point_transactions
Logic: تجمع نقاط على كل فاتورة، استبدال بخصومات
Integration: POS + CRM + Finance
```

**3. إدارة الشيكات**
```
Tables: checks, check_movements
Logic: تسجيل شيكات، تحصيل، إضافة للخزينة
```

**4. عقود التقسيط (Installments)**
```
Tables: installment_contracts, installment_details
Logic: جدول سداد، متابعة الأقساط، تذكيرات
Note: مختلف عن timeshare — ينطبق على أي بيع آجل
```

**5. WhatsApp Integration**
```
في Trucker: تطبيق مستقل Trucker Whatsapp.exe
في resort-os: tbl_whatsapp_tasks موجودة في config لكن فارغة
Needed: worker يشغّل Celery task → WhatsApp API (maavy/twilio)
```

**6. SMS Integration**
```
في Trucker: SMS log + templates + bulk SMS
في resort-os: SMS_Log في schema لكن implementation غايبة
```

**7. Granular Permissions (per-screen)**
```
في Trucker: UsersScreenAccessDetails → كل شاشة بصلاحية منفصلة
في resort-os: role-based فقط (level 30/40/60/80/100)
Needed: Permission matrix (user → action → resource)
```

**8. Branch Sync / Offline Branch**
```
في Trucker: Microsoft.Synchronization.* + PC_data tracking
في resort-os: لا يوجد — الفروع online فقط
Note: مهم لو فيه فروع في مناطق شبكة ضعيفة
```

### 🟡 ميزات مُبسَّطة تحتاج تعميق

**9. التقارير والطباعة**
- Trucker: DevExpress Reports (.repx) + pivot tables + charts
- resort-os: report_builder.py موجود لكن 0% coverage، PDF/Excel غير مكتملين
- **يحتاج:** templates للتقارير الأساسية (نهاية شيفت، كشف حساب، ميزان)

**10. Multi-currency**
- resort-os: `SUPPORTED_CURRENCIES = "EGP,USD,EUR,SAR"` في config
- لكن لا يوجد currency conversion logic أو multi-currency invoices

**11. Calendar Table للتقارير السريعة**
- Trucker: جدول تقويم مع Julian dates للـ GROUP BY السريع
- resort-os: يعتمد على date functions في PostgreSQL فقط

**12. Discount Cards / Membership**
- Trucker: bطاقات خصم + عضويات بمميزات
- resort-os: discount_engine موجود لكن بدون cards/membership system

---

## 14. خارطة الطريق الموصى بها

### المرحلة الأولى — إصلاح (2–4 أسابيع)
**أولوية قصوى قبل أي feature جديد:**

1. **إصلاح HTTP tests** — صلّح `conftest.py` واختبر على الأقل:
   - Auth endpoints (login, 2FA, token refresh)
   - Core CRUD (users, branches, modules)
   - Finance basics (invoices, payments)
   - PMS booking (conflict test)

2. **رفع timeshare/services coverage** من 31% إلى 70%+
   - contract creation
   - payment scheduling
   - exchange logic

3. **اختبار Celery tasks** بـ `task.apply()` (eager mode):
   - hr_tasks (salary calculation)
   - finance_tasks (payment reminders)

### المرحلة الثانية — ميزات من الـ Trucker (4–6 أسابيع)

4. **WhatsApp Integration**
   - Celery task موجود (`tbl_whatsapp_tasks` في schema قديم)
   - أضف `whatsapp_tasks` table + Celery worker
   - استخدم Twilio WhatsApp API أو WA Business API

5. **نظام نقاط الولاء**
   - جداول: `loyalty_programs`, `customer_points`, `point_transactions`
   - تكامل مع POS عند إغلاق الفاتورة
   - استبدال النقاط بخصومات

6. **إدارة الشيكات**
   - جداول: `checks`, `check_movements`
   - تكامل مع Finance module
   - تذكيرات تحصيل عبر Celery

7. **Order Taker App**
   - تطبيق Vue 3 جديد على port 3008
   - يستخدم `@resort-os/core` + `@resort-os/ui`
   - PWA للتابلت

### المرحلة الثالثة — تطوير وتحسين (شهر+)

8. **Granular Permissions**
   - `permissions` table: `{user_id, resource, action, allowed}`
   - Middleware/dependency يتحقق لكل endpoint
   - Admin UI لإدارة الصلاحيات

9. **Multi-currency Support**
   - `currency_rates` table (daily rates)
   - تحويل تلقائي في الفواتير
   - تقارير بعملات متعددة

10. **التقارير الكاملة**
    - إصلاح `report_builder.py`
    - templates لـ: نهاية الشيفت، كشف حساب، ميزان، راتب موظف
    - Export: PDF + Excel + Print

11. **Branch Sync (اختياري)**
    - لو محتاج offline branches
    - WebSocket sync أو event sourcing
    - يعتمد على حجم الشبكة في المنتجع

12. **Analytics Dashboard عميق**
    - Pivot tables
    - Charts تفاعلية (Chart.js أو ECharts)
    - تقارير مقارنة (شهر بشهر، سنة بسنة)

---

## ملاحق

### الأوامر الأساسية
```bash
# تشغيل المشروع
./start.sh                          # كامل
./start.sh --no-frontend            # backend فقط
./start.sh --apps="admin pos"       # frontend محدد
./status.sh                         # حالة كل خدمة
./stop.sh                           # إيقاف
./stop.sh --docker                  # إيقاف + Docker

# Backend
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8005
python app/seed.py                  # seed البيانات
alembic upgrade head                # تطبيق migrations
alembic revision --autogenerate -m "description"  # migration جديد

# Tests
pytest tests/ -q
pytest tests/ --cov=app --cov-report=term-missing -q
pytest tests/test_engines/ -q       # engines فقط
pytest tests/test_api/ -q           # API tests فقط

# Frontend
cd frontend
pnpm dev:pos                        # POS on :3001
pnpm dev:admin                      # Admin on :3004
pnpm build:all                      # build كل الـ apps
```

### Environment Variables المهمة
```env
# backend/.env
DATABASE_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/resort_os
SECRET_KEY=...                    # JWT signing key
SURVEY_TOKEN_SECRET=...           # منفصل عمداً
FIELD_ENCRYPTION_KEY=...          # Fernet key (base64)
CORS_ORIGINS=http://localhost:3001,...  # كل الـ 7 apps
ETA_ENABLED=false                 # E-Invoice مصر
```

### قواعد لا تكسرها (من CLAUDE.md)
```python
# 1. استورد get_db من app.core.database فقط
from app.core.database import get_db  # ✅ — يشارك session مع auth router

# 2. Optional fields من model_dump()
value if value is not None else default  # ✅
value or default  # ❌ لو 0 أو "" قيمة صالحة

# 3. البيانات الحساسة دايماً EncryptedString
national_id: Mapped[str | None] = mapped_column(EncryptedString(255))

# 4. Celery task جديد → سجّله في celery_app.py
# 5. role جديد → ROLE_LEVELS في deps.py
# 6. تغيير role/is_active → services.update_user_role (بيعمل revoke تلقائي)
```

### المشاريع المرتبطة (نفس الـ machine)
| مشروع | Backend Port | DB Port | الوصف |
|-------|-------------|---------|-------|
| resort-os | 8005/3001-3007 | 5436 | هذا المشروع |
| elkheima-beach-resort | 8000/5173 | 5433 | منتجع الخيمة |
| wegodivers | 8001/3000 | 5434 | Wego Divers |
| elkheima-os | 8002/3001 | — | نظام الخيمة |
| watersports-os | 8003/3002 | 5433 | رياضات مائية |
| restaurant-os | 8004/5174 | 5435 | مطعم |

