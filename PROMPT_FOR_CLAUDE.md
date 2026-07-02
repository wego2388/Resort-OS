# PROMPT — El Kheima Beach Resort OS
> استخدم هذا الملف كـ system prompt أو أول رسالة في أي جلسة Claude جديدة على هذا المشروع.

---

## هوية المشروع

**اسم المشروع (code name):** `resort-os`
**اسم التطبيق (brand name):** **El Kheima Beach**
**الوصف:** نظام إدارة منتجع سياحي متكامل (ERP + PMS + POS) — شرم الشيخ، مصر.
**الموقع:** `/home/wego/projects/resort-os/`
**Frontend app name:** `el-kheima` (كان اسمه `staff` — مُدمج في تطبيق واحد)
**Backend:** FastAPI + PostgreSQL + Redis + Celery
**Frontend:** Vue 3 + Vite + Pinia + TailwindCSS (pnpm monorepo)

---

## البنية الكاملة للمشروع

```
resort-os/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py          ← Settings (WegoSettings + resort fields)
│   │   │   ├── database.py        ← re-export من wego_core
│   │   │   ├── deps.py            ← Auth + Module guard FastAPI dependencies
│   │   │   ├── encryption.py      ← Fernet EncryptedString TypeDecorator
│   │   │   ├── module_loader.py   ← Module registry + toggle + Redis cache
│   │   │   └── rate_limit.py      ← IP-keyed rate limit middleware
│   │   ├── modules/               ← 14 module كل منهم: models/schemas/crud/services/api/router.py
│   │   │   ├── core/              ← always_on: branches, settings, users, modules, audit
│   │   │   ├── finance/           ← always_on: folios, payments, journal, cashier_shifts, ETA
│   │   │   ├── inventory/         ← always_on: warehouses, products, stock_movements, PO
│   │   │   ├── hr/                ← always_on: employees, payroll, attendance, leaves
│   │   │   ├── restaurant/        ← menu, orders, KDS (WebSocket), extras, void, hold, offline sync
│   │   │   ├── cafe/              ← مشابه restaurant بـ CRUD أبسط
│   │   │   ├── pms/               ← rooms, bookings, housekeeping, rate_plans, night_audit
│   │   │   ├── timeshare/         ← contracts, installments, visits, calendar, import-excel
│   │   │   ├── beach/             ← transactions, B2B contracts, reservations, capacity/surge
│   │   │   ├── maintenance/       ← work_orders, assets
│   │   │   ├── crm/               ← customers, leads, guest_profiles
│   │   │   ├── analytics/         ← surveys, reports, dashboards
│   │   │   ├── hub/               ← blog, contact, digital presence
│   │   │   └── leasing/           ← contracts, rent payments
│   │   ├── resort_os/             ← Pure domain engines (لا FastAPI، لا DB)
│   │   │   ├── hr_engine.py       ← حساب الراتب المصري (قانون العمل 12/2003 + ضريبة 91/2005)
│   │   │   ├── discount_engine.py ← conditional discounts
│   │   │   ├── folio_engine.py    ← folio charges validation
│   │   │   ├── beach_engine.py    ← capacity/towel/surge/B2B logic
│   │   │   ├── timeshare_engine.py← installment schedule, visit windows, ISO weeks
│   │   │   └── report_builder.py  ← PDF/Excel (wego_core.reports wrapper)
│   │   ├── tasks/                 ← Celery tasks (مسجّلة في celery_app.py)
│   │   ├── main.py                ← FastAPI app factory
│   │   ├── celery_app.py          ← Celery + beat schedule
│   │   └── seed.py                ← Idempotent seed (super_admin, branch, modules, accounts)
│   ├── tests/                     ← 508 tests، 76% coverage
│   │   ├── conftest.py            ← fixtures: client, headers per role, test DB
│   │   ├── test_api/              ← HTTP-level tests
│   │   ├── test_engines/          ← pure domain engine tests
│   │   └── test_modules/          ← service-level tests
│   ├── alembic/                   ← migrations
│   ├── requirements.txt           ← يتضمن: -e /home/wego/projects/wego-core
│   └── .env                       ← DATABASE_URL, SECRET_KEY, FIELD_ENCRYPTION_KEY, ETA_*
│
└── frontend/
    ├── packages/
    │   ├── core/                  ← @resort-os/core: API client, auth store, modules store, composables
    │   └── ui/                    ← @resort-os/ui: shared components (LoginView, etc.)
    └── apps/
        ├── el-kheima/             ← التطبيق الموحد (كان اسمه staff)
        │   ├── src/
        │   │   ├── router/index.ts← Router واحد: /pos /kds /ops /admin /waiter /portal
        │   │   ├── layouts/
        │   │   │   ├── BackOfficeLayout.vue  ← sidebar + nav (admin/ops/portal)
        │   │   │   ├── FieldLayout.vue       ← خفيف (pos/waiter)
        │   │   │   └── KioskLayout.vue       ← fullscreen (kds)
        │   │   └── views/
        │   │       ├── admin/     ← Dashboard, HR, Finance, Timeshare, CRM, etc.
        │   │       ├── pos/       ← BeachPOS, RestaurantPOS, CafePOS
        │   │       ├── kds/       ← KitchenDisplay, BarDisplay
        │   │       ├── ops/       ← Rooms, Bookings, Housekeeping, Inventory
        │   │       ├── waiter/    ← Tables, Order
        │   │       └── portal/    ← Attendance, Leaves, Payroll, Profile
        ├── public/                ← موقع العملاء (booking, home)
        └── qr/                    ← QR scanner (table menu, beach checkin)
```

---

## Ports

| Service | Port |
|---------|------|
| Backend API | 8005 |
| el-kheima (staff app) | 3001 |
| public (guest website) | 3007 |
| qr (QR scanner) | 3005 |
| PostgreSQL (Docker) | 5436 |
| Redis (Docker) | 6381 |

---

## Auth Chain

```
JWT (email-based) → get_current_user → get_current_active_user
                                              ├─ get_waiter_user      (level ≥ 30)
                                              ├─ get_cashier_user     (level ≥ 40)
                                              ├─ get_manager_user     (level ≥ 60)
                                              ├─ get_admin_user       (level ≥ 80)
                                              └─ get_super_admin_user (level ≥ 100)
```

**ROLE_LEVELS** (backend `deps.py` = frontend `useAuthStore`، نفس الأرقام):
```
super_admin=100, admin=80, accountant=70, hr_manager=70,
manager=60, supervisor=50, receptionist=40, cashier=40,
waiter=30, chef=30, kitchen=30, employee=20, customer=0, guest=0
```

**Mandatory 2FA:** `super_admin`, `accountant`
**Token revocation:** عند تغيير role/is_active → `revoke_user_tokens(user_id)` → Redis TTL = REFRESH_TOKEN_EXPIRE_DAYS

---

## Module System

كل module له `require_module("key")` FastAPI dependency.
الـ toggle: `PATCH /api/v1/core/modules/{key}` (super_admin فقط) → يحدث DB → يمسح Redis cache.
الـ frontend: `useModulesStore().isEnabled(key)` → يُفعَّل من `GET /api/v1/core/modules`.
**always_on:** core, finance, inventory, hr

**⚠️ مشكلة حالية:** `module_loader.py` يعتمد على Redis لكل request.
**الهدف:** استبداله بـ `features.py` يقرأ من `.env` مرة واحدة عند startup.

---

## wego_core — المكتبة المشتركة

موجودة في: `/home/wego/projects/wego-core/`
مثبتة كـ editable install: `-e /home/wego/projects/wego-core` في `requirements.txt`

**ما يستخدمه المشروع فعلاً:**

| Import | الغرض |
|--------|--------|
| `wego_core.models.user` | `User`, `TokenBlacklist`, `UserMixin` |
| `wego_core.models.mixins` | `TimestampMixin` (created_at, updated_at) |
| `wego_core.database` | `Base`, `get_db`, `get_engine`, `init_db` |
| `wego_core.security` | `decode_token`, `hash_token`, `get_password_hash` |
| `wego_core.cache.store` | `get_cache`, `set_cache`, `rate_limit` |
| `wego_core.auth.router` | `build_auth_router` (login/logout/2FA/register) |
| `wego_core.auth.repository` | `UserRepository` (في seed.py) |
| `wego_core.config` | `WegoSettings` (base class للـ Settings) |
| `wego_core.worker.app` | `make_celery` |
| `wego_core.reports` | `ReportBuilder` (PDF/Excel) |
| `wego_core.errors.handler` | `setup_error_handlers` |
| `wego_core.health.checker` | `build_health_router` |
| `wego_core.logging.setup` | `setup_logging` |
| `wego_core.middleware.*` | `SecurityHeadersMiddleware`, `RequestTimingMiddleware` |
| `wego_core.monitoring.sentry` | `setup_sentry` |
| `wego_core.correlation` | `CorrelationMiddleware` |

**⚠️ مشكلة VPS:** المسار `/home/wego/projects/wego-core` غير موجود على أي server آخر.
**الهدف:** نسخ `wego_core/` جوه المشروع في `backend/app/core/vendor/` وتحديث كل الـ imports.

---

## القواعد الحرجة (لا تكسرها)

```python
# 1. get_db — لازم نفس الـ callable في كل مكان
from app.core.database import get_db  # ✅ (يعيد export من wego_core)
def get_db(): ...                      # ❌ يكسر auth session sharing

# 2. Optional fields من model_dump()
value if value is not None else default   # ✅
value or default                          # ❌ لو 0/"" قيمة صالحة

# 3. حقول حساسة → EncryptedString دايماً
national_id: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)

# 4. Celery task module جديد → سجّله في celery_app.py
import app.tasks.<new_module>

# 5. role جديد → ROLE_LEVELS في deps.py وكذلك useAuthStore في frontend

# 6. تغيير role/is_active → services.update_user_role (بيعمل revoke تلقائي)
```

---

## ما تم بناؤه (الوضع الحالي)

### Backend — مكتمل بشكل جيد
- ✅ 14 module كاملة بـ models/schemas/crud/services/router
- ✅ Double-entry accounting (JournalEntry/Line/Account/AccountingPeriod)
- ✅ HR engine: راتب مصري كامل (تأمينات + ضرائب شرائح + بدلات + جزاءات)
- ✅ Beach engine: capacity/towel/surge/B2B validation
- ✅ Timeshare engine: ISO week calendar, installment schedules, visit windows
- ✅ Discount engine: conditional discounts (amount/count/day/group)
- ✅ Folio engine: charge validation, checkout rules
- ✅ Offline POS sync (IndexedDB queue → `/restaurant/orders/sync`)
- ✅ CashierShift: open/close + variance
- ✅ Void order items (مع سبب + توثيق)
- ✅ Hold orders (held status)
- ✅ Menu extras/modifiers (ExtraGroup + min/max select)
- ✅ WebSocket KDS
- ✅ QR public menu + guest orders
- ✅ ETA e-invoice (مصر) — disabled بـ ETA_ENABLED=false
- ✅ Timeshare Excel import (idempotent via form_number)
- ✅ 508 tests، 76% coverage

### Frontend — هيكل موحّد جديد
- ✅ تطبيق واحد `el-kheima` بدل 8 apps منفصلة
- ✅ Router واحد مع role-based routing (`homeRouteFor(role)`)
- ✅ Module guard في router + nav (لا يظهر زر لـ module معطّل)
- ✅ Boot sequence صحيح (await fetchUser + fetchModules قبل router)
- ✅ 3 layouts: BackOffice / Field / Kiosk
- ✅ ROLE_LEVELS متطابق backend ↔ frontend
- ✅ `useOfflineQueue()` لـ POS + waiter
- ✅ PWA manifest شامل

### الـ Apps القديمة — تم حذفها ✅ (2026-07-01)
`admin, pos, kds, ops, waiter, portal` اتحذفوا نهائياً من `apps/` بعد browser walkthrough حقيقي (Playwright)
أكّد إن `el-kheima` بيغطي كل سيناريوهات الـ login/role-redirect/nav-filtering/gated-route-redirect بتاعتهم.
اكتُشفت واتصلحت أثناء التأكد: (1) `GET /api/v1/auth/me` مش موجودة في `wego_core` — تمت إضافتها كـ endpoint
محلي resort-os-only (`backend/app/core/me_router.py`)، (2) `useModulesStore` كانت بتقرا حقل غلط
(`is_enabled` بدل `enabled`) فكانت دايماً بترجع false، (3) router guard كان لازم يعمل
`await modules.fetchEnabled()` بنفسه (مش بس في `main.ts` boot) وإلا login تفاعلي يعمل infinite redirect
loop. التفاصيل الكاملة في `CLAUDE.md` § 5 وmemory `project_resort_os.md`.

---

## المشاكل الحرجة المعلّقة (مرتبة بالأولوية)

### 🔴 حرجة — توقف الإنتاج

1. **wego-core dependency** — المشروع لا يعمل على أي VPS آخر بدون `/home/wego/projects/wego-core`
   - **الحل:** نسخ `wego_core/` → `backend/app/core/vendor/` + بدّل 24 ملف بـ sed

2. **Module system يعتمد على Redis لكل request** — لو Redis down المشروع يعتقد كل module معطّل
   - **الحل:** استبدال `module_loader.py` بـ `features.py` يقرأ `.env` مرة واحدة

3. ~~الـ apps القديمة لا تزال في workspace~~ — **تم الحذف 2026-07-01** (`admin, pos, kds, ops, waiter,
   portal` مش موجودين في `apps/` خالص دلوقتي، و`start.sh`/`stop.sh`/`status.sh` بيشغّلوا `el-kheima` بس)

### 🟡 مهمة — ناقصة للإنتاج الحقيقي

4. **Financial Reports** — مفيش trial balance / income statement / balance sheet
   - الجداول موجودة (JournalEntry, Account, AccountingPeriod) لكن مفيش aggregate endpoints

5. **Z-Report / Shift End Report** — تقرير نهاية الوردية للطباعة (roll printer + A4)
   - `CashierShift` موجود، `ShiftEndReport` schema موجود، لكن مفيش PDF output

6. **Night Audit Celery Beat** — لازم يشتغل تلقائي كل يوم الساعة 3 صباحاً
   - يحوّل bookings → occupied، يـ post room charges على folios، يـ generate audit log

7. **Inventory → Restaurant linkage** — stock مش بينزل لما تبيع وجبة

8. **`localStorage` token** — مشكلة XSS — الأفضل `httpOnly cookie`

9. ~~`LoginView` في `@resort-os/ui` — مش واضح إنها exported بشكل صح~~ — **تم التأكد 2026-07-01**: `export
   { default as LoginView } from './views/LoginView.vue'` موجود في `packages/ui/src/index.ts` ومُختبَر live
   (Playwright) — الـ login flow بيشتغل فعلاً end-to-end.

### 🟢 تحسينات مهمة من Trucker (البرنامج القديم)

10. **POS_Money_Count** — عدّ فئات العملة (50 جنيه × 10 = 500) عند إغلاق الشيفت
11. **KDS per-category** — كل شاشة مطبخ تعرض categories معينة بس (مش كل الطلبات)
12. **Screen-level permissions** — CanShow/CanAdd/CanEdit/CanDelete per screen per user
13. **Auto-posting** — كل فاتورة تولّد journal entry تلقائي عبر `JL_AccountsLink`

---

## المميزات الفريدة (لا تتراجع عنها)

هذه ميزات في resort-os أفضل من البرامج القديمة المرجعية:

- **الشاطئ (Beach)** — domain كامل غير موجود في الأنظمة الأخرى
  - capacity tracking، surge pricing، B2B hotel contracts، towel management
- **Timeshare** — عمق تاريخ الزيارات ISO calendar، أقساط متعددة، Excel import
- **Security** — JWT email-based + 2FA + token revocation + Fernet field encryption
- **Architecture** — REST API حقيقي، لا stored procedures، web-based على أي device
- **Offline POS** — IndexedDB queue → sync FIFO، يشتغل بدون نت

---

## Environment Variables الأساسية

```env
# .env (backend)
DATABASE_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/resort_os
SECRET_KEY=<random 64 chars>
FIELD_ENCRYPTION_KEY=<Fernet key — python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
SURVEY_TOKEN_SECRET=<random 32 chars>
CORS_ORIGINS=http://localhost:3001,http://localhost:3005,http://localhost:3007

# ETA (Egyptian Tax Authority) — disabled by default
ETA_ENABLED=false
ETA_CLIENT_ID=
ETA_CLIENT_SECRET=
ETA_TAXPAYER_RIN=
ETA_TAXPAYER_NAME=

# Feature flags (كل حاجة enabled افتراضياً — عطّل اللي مش محتاجه)
# FEATURE_TIMESHARE=false
# FEATURE_LEASING=false
# FEATURE_CAFE=false

# Resort config
RESORT_NAME=El Kheima Beach
VAT_PERCENTAGE=14.0
SERVICE_CHARGE_PERCENTAGE=12.0
TIMEZONE=Africa/Cairo
DEFAULT_CURRENCY=EGP
```

---

## تشغيل المشروع

```bash
# Development
./start.sh                          # كل حاجة
./start.sh --no-frontend            # backend فقط
./start.sh --apps="el-kheima qr"   # frontend apps محددة

# Tests
cd backend && source .venv/bin/activate
pytest tests/ -q                    # 508 tests
pytest tests/ --cov=app --cov-report=term-missing -q   # مع coverage

# Database
cd backend && source .venv/bin/activate
alembic upgrade head                # run migrations
python -m app.seed                  # seed initial data
```

**Login الافتراضي:** `admin@resortos.local` / `Admin@123456` (super_admin — يحتاج 2FA)

---

## أولويات العمل القادم

### المرحلة 1 — Self-Contained (ضروري قبل أي VPS deployment)
```
[ ] نسخ wego_core → backend/app/core/vendor/
[ ] sed -i 's/from wego_core./from app.core.vendor./g' على 24 ملف
[ ] حذف -e /home/wego/projects/wego-core من requirements.txt
[ ] تشغيل pytest — لازم 508 tests تعدي
[ ] استبدال module_loader.py بـ features.py (env-based, no Redis)
[x] حذف apps القديمة (`admin/pos/kds/ops/waiter/portal` اتشالوا فعلاً من `apps/` — 2026-07-01؛
    `pnpm-workspace.yaml` أصلاً بيستخدم glob `apps/*` فمحتاجش تعديل)
[x] تحديث start.sh/stop.sh/status.sh للـ el-kheima بدل 8 apps
```

### المرحلة 2 — إنتاج حقيقي
```
[ ] Financial Reports: GET /finance/reports/trial-balance | income-statement | balance-sheet
[ ] Z-Report PDF: GET /finance/shifts/{id}/report (roll + A4)
[ ] Night Audit Celery Beat: @celery_app.on_after_configure → cron 03:00 Cairo time
[ ] Inventory deduction عند confirm order في restaurant
[ ] POS Money Count model للشيفت
[ ] LoginView في @resort-os/ui موجودة ومصدّرة
[ ] httpOnly cookie للـ JWT token
```

### المرحلة 3 — VPS Deployment
```
[ ] docker-compose.yml (postgres + redis + backend + frontend + nginx)
[ ] nginx.conf: /api → :8005, /ws → :8005, / → :3001
[ ] SSL بـ certbot
[ ] Environment secrets في .env.production (لا في git)
[ ] Health check endpoint
[ ] Sentry DSN للـ error tracking
```

---

## ملاحظات تقنية هامة

### gotchas موثّقة (لا تتجاهلها)

1. **`get_db` sharing** — `build_auth_router()` يستخدم `wego_core.database.get_db` داخلياً. لو `app.core.deps.get_db` كان callable منفصل، FastAPI سيفصل الـ sessions وأي تعديل على `user` object لن يُحفظ. الحل في `database.py`: re-export من wego_core مباشرة.

2. **`dict.get()` مع None** — `model_dump()` على Pydantic Optional fields يعطي `None` للـ keys غير المبعوتة. `dict.get(key, default)` يُرجع `None` مش الـ default. استخدم `value if value is not None else default`.

3. **`AuthService(db, user_model, settings)`** — 3 arguments إجبارية في wego_core، مفيهاش `get_current_user`. مبنية في `deps.py`.

4. **Migration heads** — راجع `alembic heads` قبل أي migration جديد. كان فيه 3 heads متفرقة اتدمجت.

5. **Celery tasks** — كل task module جديد لازم يتستورد في آخر `celery_app.py` وإلا الـ beat schedule يفشل بـ "unregistered task".

6. **`useModulesStore` قبل Pinia** — في `router/index.ts`، الـ redirect function `() => homeRouteFor(useAuthStore().role)` بتتنفذ في runtime مش في load time. لكن انتبه لأي استخدام للـ stores خارج `beforeEach`.

7. **`EncryptedString`** — مبنية كـ TypeDecorator، شفافة تماماً في الكود. مستخدمة على: `employees.national_id`, `bookings.guest_national_id`, `timeshare_contracts.customer_national_id`, `lease_contracts.tenant_national_id`, `crm_customers.national_id`, `guest_profiles.national_id`.

8. **Room locking** — `pms/services.create_booking()` يستخدم `SELECT FOR UPDATE NOWAIT` لمنع double-booking. لا يعمل على SQLite — اختبره على Postgres فقط.

### Coverage الحالي (الضعيف يحتاج attention)
```
analytics/api/router.py    30%   ← الأكثر إهمالاً
finance/api/router.py      41%   ← حرج — محاسبة
hr/api/router.py           49%   ← مهم
timeshare/api/router.py    58%   ← واحد من أكبر modules
restaurant/api/router.py   63%   ← أكثر استخداماً
```

---

## الرجاء من Claude

عند العمل على هذا المشروع:

1. **اقرأ الكود قبل الكتابة** — لا تفترض أي شيء. اقرأ الملف المعني قبل التعديل.

2. **حافظ على الـ patterns الموجودة:**
   - Backend: `crud` ← لا HTTPException | `services` ← ValueError | `router` ← يترجم الأخطاء
   - Frontend: `useAuthStore` + `useModulesStore` لكل قرار routing/visibility

3. **لا تكسر 508 tests** — شغّل `pytest tests/ -q` بعد أي تغيير backend.

4. **المشروع اسمه "El Kheima Beach"** في كل documentation وـ UI وـ API docs. اسم الـ package يفضل `resort-os`.

5. **الـ wego-core imports** — لو طُلب منك دمج wego-core، اتبع الخطوة: `cp -r wego_core → app/core/vendor/` ثم `sed` على كل الـ imports، ثم run tests.

6. **أسلوب الكود:**
   - Python: type hints كاملة، `Mapped[...]` لـ SQLAlchemy، `Decimal` للأموال (لا float)
   - Vue: Composition API، `<script setup lang="ts">`, TailwindCSS classes
   - لغة التعليقات: عربي في business logic، إنجليزي في تقني

7. **الأمان غير قابل للتفاوض:**
   - كل endpoint حساس: `Depends(require_module(...))` + `Depends(get_role_user(...))`
   - حقول PII: `EncryptedString` دايماً
   - أي تغيير role/is_active: `revoke_user_tokens()` لازم يتنادى

8. **لا تعيد بناء ما يشتغل** — المشروع فيه 32,000 سطر Python ناضجة. أي إعادة بناء كاملة تكلف 3-6 أشهر للوصول لنفس النقطة. ركّز على إضافة الناقص وإصلاح المشاكل الحرجة.

---

*آخر تحديث: 2026-07-01 — بعد الفحص الكامل للمشروع وتحليل Trucker ERP (138 جدول، production system)*
