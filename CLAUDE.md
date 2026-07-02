# El Kheima Beach — Engineering Charter
> **الاستخدام:** افتح هذا الملف في أول رسالة لأي جلسة Claude على هذا المشروع.
> هذا الملف يجمع بين هوية المشروع الكاملة + معايير الهندسة + القواعد الحرجة.

---

## § 0 — هويتك في هذا المشروع

أنت لا تعمل كـ chatbot.

أنت **Principal Software Architect + Senior Backend/Frontend/DevOps/Security Engineer + QA Lead** في نفس الوقت على مشروع تجاري حقيقي.

مسؤوليتك ليست كتابة كود بسرعة.
مسؤوليتك تسليم **software جاهز للإنتاج** — نظيف، قابل للصيانة، آمن، مختبر، وقابل للتوسع.

كل ملف تلمسه → اتركه أفضل مما وجدته.
لا تنتج حلولاً مؤقتة. لا تنتج demo code. لا تخفّض جودة Architecture للراحة.

---

## § 1 — هوية المشروع

| | |
|--|--|
| **Code name** | `resort-os` |
| **Brand name** | **El Kheima Beach** |
| **النوع** | ERP + PMS + POS — منتجع سياحي شرم الشيخ |
| **الموقع** | `/home/wego/projects/resort-os/` |
| **Backend** | FastAPI + PostgreSQL + Redis + Celery |
| **Frontend** | Vue 3 + Vite + Pinia + TailwindCSS (pnpm monorepo) |
| **Staff App** | `el-kheima` (port 3001) |
| **Guest Website** | `public` (port 3007) |
| **QR Scanner** | `qr` (port 3005) |
| **Backend API** | port 8005 |
| **PostgreSQL** | port 5436 (Docker) |
| **Redis** | port 6381 (Docker) |

---

## § 2 — Architecture Map

```
resort-os/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py          ← Settings (WegoSettings base + resort fields)
│   │   │   ├── database.py        ← re-export من wego_core (⚠️ لا تعيد تعريفه)
│   │   │   ├── deps.py            ← Auth chain + require_module + rate_limit_dep
│   │   │   ├── encryption.py      ← Fernet EncryptedString TypeDecorator
│   │   │   ├── module_loader.py   ← Module registry + DB/Redis toggle
│   │   │   └── rate_limit.py      ← IP-keyed middleware
│   │   │
│   │   ├── modules/               ← 14 module، كل منهم:
│   │   │   │                         models → schemas → crud → services → api/router
│   │   │   ├── core/              ← always_on: branches, settings, users, audit
│   │   │   ├── finance/           ← always_on: folios, payments, journal, shifts, ETA
│   │   │   ├── inventory/         ← always_on: warehouses, products, stock
│   │   │   ├── hr/                ← always_on: employees, payroll, attendance, leaves
│   │   │   ├── restaurant/        ← menu, orders, KDS WebSocket, extras, void, hold
│   │   │   ├── cafe/
│   │   │   ├── pms/               ← rooms, bookings, housekeeping, rate_plans
│   │   │   ├── timeshare/         ← contracts, installments, visits, Excel import
│   │   │   ├── beach/             ← transactions, B2B, capacity/surge
│   │   │   ├── maintenance/
│   │   │   ├── crm/
│   │   │   ├── analytics/
│   │   │   ├── hub/
│   │   │   └── leasing/
│   │   │
│   │   ├── resort_os/             ← Pure Domain Engines (لا FastAPI، لا DB)
│   │   │   ├── hr_engine.py       ← راتب مصري: قانون العمل 12/2003 + ضريبة 91/2005
│   │   │   ├── discount_engine.py
│   │   │   ├── folio_engine.py
│   │   │   ├── beach_engine.py    ← capacity/towel/surge/B2B
│   │   │   ├── timeshare_engine.py← ISO weeks, installments, visit windows
│   │   │   └── report_builder.py
│   │   │
│   │   ├── tasks/                 ← Celery tasks (كل module جديد → سجّله في celery_app.py)
│   │   ├── main.py
│   │   ├── celery_app.py
│   │   └── seed.py                ← Idempotent
│   │
│   ├── tests/                     ← 508 tests، 76% coverage
│   ├── alembic/
│   └── requirements.txt           ← ⚠️ يتضمن: -e /home/wego/projects/wego-core
│
└── frontend/
    ├── packages/
    │   ├── core/  ← @resort-os/core: API client, auth store, modules store
    │   └── ui/    ← @resort-os/ui: LoginView + shared components
    └── apps/
        ├── el-kheima/   ← التطبيق الموحد: /pos /kds /ops /admin /waiter /portal
        ├── public/
        └── qr/
```

**قاعدة Architecture لا تُكسر:**
```
crud.py       ← DB operations فقط، لا HTTPException
services.py   ← Business logic، يرمي ValueError (→400) أو custom exception
api/router.py ← HTTP layer فقط، يترجم الأخطاء
resort_os/    ← Pure Python، لا imports من FastAPI أو SQLAlchemy
```

---

## § 3 — Auth Chain

```
JWT (email-based, DB lookup كل request)
    → get_current_user         ← decode + blacklist check + revocation check
        → get_current_active_user  ← is_active + mandatory-2FA gate
            ├─ get_waiter_user       level ≥ 30
            ├─ get_cashier_user      level ≥ 40
            ├─ get_manager_user      level ≥ 60
            ├─ get_admin_user        level ≥ 80
            └─ get_super_admin_user  level ≥ 100
```

**ROLE_LEVELS — متطابقة تماماً في `deps.py` و `useAuthStore.ts`:**
```
super_admin=100  admin=80    accountant=70  hr_manager=70
manager=60       supervisor=50  receptionist=40  cashier=40
waiter=30        chef=30     kitchen=30     employee=20
customer=0       guest=0
```

**2FA إجباري:** `super_admin`, `accountant`
**Token revocation:** عند تغيير role/is_active → `revoke_user_tokens(user_id)` → Redis

---

## § 4 — Module System

```python
# كل endpoint محمي بـ:
@router.get("/orders", dependencies=[Depends(require_module("restaurant"))])
async def list_orders(user=Depends(get_cashier_user), db: DbDep = ...):
    ...
```

- Toggle: `PATCH /api/v1/core/modules/{key}` (super_admin) → DB → Redis invalidate
- Frontend: `useModulesStore().isEnabled(key)` — يُقيَّم في router guard + nav
- `always_on`: core, finance, inventory, hr — لا تحتاج check

---

## § 5 — القواعد الحرجة (Project-Specific Gotchas)

هذه ليست نظرية — هي أخطاء وقعت فعلاً في هذا المشروع:

```python
# ❶ get_db — نفس الـ callable في كل مكان (لا تعيد تعريفه أبداً)
from app.core.database import get_db  # ✅ re-export من wego_core
def get_db(): ...                      # ❌ يكسر auth session، التعديلات لا تُحفظ

# ❷ Optional fields من Pydantic model_dump()
value if value is not None else default   # ✅ (0 و "" قيم صالحة)
value or default                          # ❌ يفشل مع 0/False/""

# ❸ حقول PII — EncryptedString إجباري
national_id: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
# مُطبَّقة على: employees، bookings، timeshare_contracts، crm_customers، guest_profiles

# ❹ Celery task module جديد → سجّله في celery_app.py
import app.tasks.<new_module>  # في آخر الملف — وإلا beat يفشل بـ "unregistered task"

# ❺ role جديد → ROLE_LEVELS في deps.py + useAuthStore.ts (نفس الأرقام)

# ❻ تغيير role/is_active → لازم تنادي revoke_user_tokens()
# استخدم services.update_user_role() — مش user.role = ... مباشرة

# ❼ الأموال → Decimal دايماً، مش float
amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # ✅
amount: float = ...  # ❌

# ❽ Room double-booking → SELECT FOR UPDATE NOWAIT (Postgres فقط، مش SQLite)

# ❾ alembic heads → تحقق قبل أي migration جديد
# كان فيه 3 heads متفرقة — تأكد من head واحد
```

**فرونت إند — اتكتشفوا وقت دمج الـ 6 apps القديمة في `el-kheima` (2026-07-01):**

- ❿ **مفيش `GET /api/v1/auth/me` في `wego_core.auth.router`** — الـ endpoint اللي `useAuthStore.fetchUser()`
  بيعتمد عليه. اتحل بـ endpoint محلي resort-os-only (`backend/app/core/me_router.py`، مش تعديل على
  wego-core نفسه) مُركّب على نفس الـ prefix (`{API_PREFIX}/auth`) فالـ URL طابق `ENDPOINTS.auth.me` بدون
  أي تغيير frontend. الـ response مفيهوش `branch_id` — عمود `branch_id` مش موجود خالص في
  `wego_core.models.user.User` (تحقّقنا من الـ DB مباشرة)، فـ `useAuthStore.branchId` بيرجع دايماً fallback
  `1` — ده pre-existing limitation مش regression (الـ 6 apps القديمة كانت بتعمل نفس الـ fallback من
  localStorage). حل حقيقي محتاج قرار data-model أكبر (user→branch assignment)، مش تحسين frontend بسيط.
- ⓫ `GET /api/v1/modules` بيرجّع `enabled`، مش `is_enabled` — `@resort-os/core`'s `Module` type/`useModulesStore`
  كانوا بيقروا حقل مش موجود، فـ `isEnabled()` كان دايماً `false` بصمت (dead code من زمان الـ scaffolding
  الأول، محدش لاحظ لحد ما الـ router guard الجديد بدأ يستخدمه فعلياً). اتصلح في `packages/core`.
- ⓬ **Router guard لازم يكون async ويعمل `await modules.fetchEnabled()` بنفسه لو الـ store لسه فاضي** —
  مش كفاية إنك تعمل الـ fetch في `main.ts`'s boot() بس. `main.ts` بتغطي حالة الـ page reload (session
  restore من localStorage)، لكن login تفاعلي (`useAuthStore.login()` من جوه `LoginView`) بيعدي مباشرة
  من غير ما يمر على boot() تاني — فلو الـ guard مش بيعمل fetch بنفسه، الـ modules store بيفضل فاضي بعد
  أي login جديد، وأي route فيها `meta.module` بترجع `false` فوراً، وبما إن `homeRouteFor(role)` نفسه بيروح
  لـ route فيها module gate، النتيجة infinite redirect loop بين `/login` والـ home route — ده اكتُشف
  فعلياً في live browser test (Playwright)، مش نظري.

---

## § 6 — wego_core Dependency

**⚠️ مشكلة حرجة للـ VPS:** مثبّت كـ `-e /home/wego/projects/wego-core` — هذا المسار غير موجود على أي server آخر.

**ما يستخدمه المشروع (24 ملف):**
`User`, `TokenBlacklist`, `TimestampMixin`, `Base/get_db/init_db`, `decode_token/hash_token/get_password_hash`, `get_cache/set_cache/rate_limit`, `build_auth_router`, `UserRepository`, `WegoSettings`, `make_celery`, `ReportBuilder`, `setup_error_handlers`, `build_health_router`, `setup_logging`, `SecurityHeadersMiddleware`, `RequestTimingMiddleware`, `setup_sentry`, `CorrelationMiddleware`

**الحل المُقرَّر:** `cp -r wego_core/ → backend/app/core/vendor/` ثم sed على كل الـ imports، ثم حذف `-e path` من requirements.txt

---

## § 7 — سير العمل الهندسي الإلزامي

لكل طلب، اتبع هذا الترتيب بالضبط:

### 7.1 — قيّم حجم الطلب أولاً

```
طلب صغير (typo, rename, config) → نفّذ فوراً
طلب متوسط (endpoint جديد, bugfix)  → scan سريع ثم نفّذ
طلب كبير (feature, module, migration) → خطوات 7.2 → 7.8 كاملة
```

### 7.2 — افهم الصورة كاملة قبل أي سطر كود

حدّد:
- الـ modules المتأثرة
- تأثير على DB (migration؟)
- تأثير على API (breaking change؟)
- تأثير على Frontend (types، stores، router؟)
- تأثير على Security (أي permission جديد؟)
- تأثير على Performance (N+1؟ index؟)
- تأثير على Tests (هل 508 tests لا تزال تعدي؟)

### 7.3 — ابحث قبل أن تنشئ

قبل كتابة أي كود جديد، تحقق:
- هل هذا الـ model موجود في modules أخرى؟
- هل هذه الـ utility موجودة في `resort_os/` أو `core/`؟
- هل هذا الـ composable موجود في `packages/core`؟

**لا تكرر كوداً موجوداً.**

### 7.4 — نفّذ باستخدام Architecture المشروع فقط

- لا تضيف layer جديدة غير موجودة
- لا تخترق الـ layering (router لا يكلّم DB مباشرة)
- لا تنشئ utilities خارج `core/` أو `resort_os/`

### 7.5 — نظّف بعد التنفيذ فوراً

احذف:
- imports غير مستخدمة
- variables مؤقتة
- كود مكرر
- commented code
- dead branches

### 7.6 — راجع عملك كـ code reviewer خارجي

ابحث عن:
- Race conditions (خاصةً في bookings وshift open/close)
- Null dereferences
- Missing permission checks
- N+1 queries
- Decimal vs float
- Missing encryption للـ PII fields

### 7.7 — تحقق من الاتساق الكامل

إذا تغيّر شيء في Backend:
```
model تغيّر → schema تغيّر → crud تغيّر → service تغيّر → router تغيّر
                                                              ↓
                                                          types.ts تغيّر
                                                              ↓
                                                          store/composable تغيّر
                                                              ↓
                                                          test تحدّث
```

### 7.8 — تحقق من الـ Production Readiness

```
☐ Architecture محترمة
☐ لا كود مكرر
☐ لا dead code
☐ Types صحيحة (Decimal للأموال، Mapped[] للـ SQLAlchemy)
☐ Permissions صحيحة (require_module + role guard)
☐ PII مشفّرة
☐ Error handling كامل
☐ لا N+1 queries
☐ pytest tests/ -q لا يزال يعطي 508 passed
☐ alembic upgrade head يعمل بدون errors
```

---

## § 8 — Security Rules

الأمان غير قابل للتفاوض في هذا المشروع (بيانات ضيوف حقيقيين):

- كل endpoint: `Depends(require_module(...))` + `Depends(get_role_user(...))`
- كل حقل PII (رقم قومي، جواز سفر): `EncryptedString` إلزامياً
- كل تغيير role/is_active: `revoke_user_tokens()` إلزامياً
- لا تعرض internal errors للـ client (404 وليس "table not found")
- لا تثق في JWT claims — اعمل DB lookup حقيقي كل request
- Rate limiting موجود على login (5/300s) وـ public endpoints (30/60s)

---

## § 9 — Database Rules

- لا تحذف column بدون migration + backfill
- الأموال: `Numeric(12, 2)` + `Decimal` في Python — لا `float` أبداً
- لا تغيّر schema بدون تحقق من `alembic heads` أولاً
- Row locking للـ concurrent operations: `SELECT FOR UPDATE NOWAIT`
- Index على كل column يُستخدم في WHERE أو JOIN متكرر
- Pagination على كل list endpoint — لا تُرجع آلاف الـ rows

---

## § 10 — Code Style

```python
# Python
# - Type hints كاملة
# - Mapped[...] لـ SQLAlchemy ORM
# - Decimal للأموال
# - تعليقات: عربي للـ business logic، إنجليزي للتقني
```

```typescript
// TypeScript / Vue
// - Composition API + <script setup lang="ts">
// - TailwindCSS (لا inline styles)
// - useAuthStore + useModulesStore لكل قرار routing/visibility
// - لا hardcode للـ business rules في الـ UI
```

---

## § 11 — الوضع الحالي والمشاكل المعلّقة

### ✅ مكتمل
- 14 module (models/schemas/crud/services/router)
- Domain engines: HR (راتب مصري)، Beach، Timeshare، Discount، Folio
- Double-entry accounting (Journal/Account/Period) — **بدون financial reports بعد**
- Offline POS، KDS WebSocket، QR menu، ETA e-invoice
- 508 tests، 76% coverage
- Frontend موحّد: `el-kheima` مع role-based routing، 3 layouts، module guard

### 🔴 حرجة (تمنع VPS deployment)
1. `wego-core` editable local path → الحل: vendor في `app/core/vendor/`
2. Module system يعتمد على Redis → الحل: `features.py` env-based
3. ~~Apps قديمة (admin/pos/kds/ops/waiter/portal) لا تزال في workspace~~ — **تم الحذف 2026-07-01**
   بعد التأكد الفعلي (browser walkthrough حقيقي بـ Playwright، مش curl بس) من إن `el-kheima` بيغطي كل الـ 6
   apps القديمة صح: login → role-based home صحيح، nav بيتفلتر حسب role/module، direct URL لـ route محمي
   بيعمل redirect مش render-then-403. تفاصيل كاملة (المسارات، الـ layouts التلاتة، الـ gotchas) في § 5
   (❿-⓬ فوق) وفي memory `project_resort_os.md`.

### 🟡 ناقصة للإنتاج الحقيقي
4. Financial Reports: trial balance، income statement، balance sheet
5. Z-Report / Shift End Report (PDF، roll + A4)
6. Night Audit Celery Beat (03:00 Cairo، auto-post room charges)
7. Inventory deduction عند confirm order في restaurant
8. `localStorage` token → `httpOnly cookie`
9. `LoginView` في `@resort-os/ui` — تحقق من export

### 🟢 تحسينات مستقبلية
10. POS Money Count (فئات العملة عند إغلاق الشيفت)
11. KDS per-category (كل شاشة مطبخ = categories محددة)
12. Screen-level permissions (CanShow/CanAdd/CanEdit/CanDelete)
13. Auto-posting (كل فاتورة → journal entry تلقائي)

---

## § 12 — Coverage الحالي (يحتاج attention)

```
analytics/api/router.py    30%  ← أولوية قصوى
finance/api/router.py      41%  ← حرج (محاسبة)
hr/api/router.py           49%
timeshare/api/router.py    58%
restaurant/api/router.py   63%
```
قبل أي feature جديد في هذه الـ modules، أضف HTTP-level tests أولاً.

---

## § 13 — تشغيل المشروع

```bash
# Backend
./start.sh                        # كل حاجة
./start.sh --no-frontend          # backend فقط
./start.sh --apps="el-kheima qr"  # frontend محدد

# Tests (لا تكمل أي task قبل ما 508 tests تعدي)
cd backend && source .venv/bin/activate
pytest tests/ -q
pytest tests/ --cov=app --cov-report=term-missing -q

# Database
alembic upgrade head
python -m app.seed
```

**Login:** `admin@resortos.local` / `Admin@123456` (super_admin — 2FA required)

---

## § 14 — Environment Variables الأساسية

```env
DATABASE_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/resort_os
SECRET_KEY=<64 random chars>
FIELD_ENCRYPTION_KEY=<Fernet key>
SURVEY_TOKEN_SECRET=<32 random chars>
CORS_ORIGINS=http://localhost:3001,http://localhost:3005,http://localhost:3007
RESORT_NAME=El Kheima Beach
VAT_PERCENTAGE=14.0
SERVICE_CHARGE_PERCENTAGE=12.0
TIMEZONE=Africa/Cairo
DEFAULT_CURRENCY=EGP
ETA_ENABLED=false
# Feature flags (كل حاجة enabled افتراضياً)
# FEATURE_TIMESHARE=false
# FEATURE_LEASING=false
```

---

## § 15 — ما لا تفعله أبداً

```
❌ لا تعيد بناء ما يشتغل (32,000 سطر Python ناضجة)
❌ لا تنشئ get_db جديد — فقط import من app.core.database
❌ لا تستخدم float للأموال
❌ لا تخزّن PII بدون EncryptedString
❌ لا تغيّر role/is_active بدون revoke_user_tokens()
❌ لا تضيف Celery task بدون تسجيله في celery_app.py
❌ لا تضيف migration بدون التحقق من alembic heads
❌ لا تُرجع list endpoint بدون pagination
❌ لا تكسر 508 tests
```

---

*آخر تحديث: 2026-07-01*
*المشروع يستخدم: [resort-os GitHub] · FastAPI 0.115 · SQLAlchemy 2.0 · Pydantic v2 · Vue 3.4 · pnpm*
