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
│   │   │   ├── config.py          ← Settings (CoreSettings base + resort fields)
│   │   │   ├── database.py        ← re-export من app.core.kernel.database (⚠️ لا تعيد تعريفه)
│   │   │   ├── deps.py            ← Auth chain + rate_limit_dep
│   │   │   ├── encryption.py      ← Fernet EncryptedString TypeDecorator
│   │   │   ├── rate_limit.py      ← IP-keyed middleware
│   │   │   └── kernel/            ← البنية التحتية المملوكة بالكامل (auth/security/cache/...) — راجع §6
│   │   │
│   │   ├── modules/               ← 14 module، كل منهم دايمًا شغال (مفيش تفعيل/تعطيل):
│   │   │   │                         models → schemas → crud → services → api/router
│   │   │   ├── core/              ← branches, settings, users, audit
│   │   │   ├── finance/           ← folios, payments, journal, shifts, ETA
│   │   │   ├── inventory/         ← warehouses, products, stock
│   │   │   ├── hr/                ← employees, payroll, attendance, leaves
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
│   ├── tests/                     ← 753 tests
│   ├── alembic/
│   └── requirements.txt           ← كل الاعتماديات pinned، مفيش أي editable local path
│
└── frontend/
    ├── packages/
    │   ├── core/  ← @resort-os/core: API client, auth store
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

## § 4 — لا يوجد نظام تفعيل/تعطيل موديولات

**قرار معماري متعمد (2026-07-02)**: كل الـ 14 موديول دايمًا شغالة، زي `core`/`finance` قبل كده تمامًا —
مفيش `require_module()`، مفيش `ModuleState` في الداتابيز، مفيش `useModulesStore` في الفرونت إند.
كان فيه نظام dynamic toggle (DB+Redis-cached، تفعيل/تعطيل فوري بدون restart) لكن اتشال بالكامل لأن
المشروع منتجع واحد مش منتج SaaS بيتباع لعملاء بمزايا مختلفة — الحماية الوحيدة الباقية على كل endpoint
هي الـ role/permission gates العادية (`get_cashier_user`، `get_manager_user`، إلخ).

---

## § 5 — القواعد الحرجة (Project-Specific Gotchas)

هذه ليست نظرية — هي أخطاء وقعت فعلاً في هذا المشروع:

```python
# ❶ get_db — نفس الـ callable في كل مكان (لا تعيد تعريفه أبداً)
from app.core.database import get_db  # ✅ re-export من app.core.kernel.database
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

- ❿ **مفيش `GET /api/v1/auth/me` في `app.core.kernel.auth.router`** — الـ endpoint اللي
  `useAuthStore.fetchUser()` بيعتمد عليه (الـ kernel's auth router عام، مش خاص بمشروع معين، فمفيهوش
  `branch_id`). اتحل بـ endpoint محلي resort-os-only (`backend/app/core/me_router.py`) مُركّب على نفس
  الـ prefix (`{API_PREFIX}/auth`) فالـ URL طابق `ENDPOINTS.auth.me` بدون أي تغيير frontend. الـ
  response مفيهوش `branch_id` — عمود `branch_id` مش موجود خالص في `app.core.kernel.models.user.User`،
  فـ `useAuthStore.branchId` بيرجع دايماً fallback `1` — ده pre-existing limitation مش regression
  (الـ 6 apps القديمة كانت بتعمل نفس الـ fallback من localStorage). حل حقيقي محتاج قرار data-model
  أكبر (user→branch assignment)، مش تحسين frontend بسيط.
---

## § 6 — app/core/kernel/ (البنية التحتية المملوكة بالكامل)

**قرار معماري متعمد (2026-07-03)**: resort-os **مستقل 100%** — مفيش أي اعتماد على `wego_core` أو أي
باكدج خارجي مشترك. كل البنية التحتية (auth, security, database session, cache, error handling,
health checks, logging, Sentry, Celery factory, WhatsApp/email notifications, PDF/Excel reports)
منقولة بالكامل وبقت كود مملوك في `backend/app/core/kernel/` — مش نسخة "vendored" بتتزامن مع مصدر
خارجي، كود resort-os نفسه، تقدر تعدّله زي أي جزء تاني من المشروع من غير استئذان.

```
app/core/kernel/
├── config.py          ← CoreSettings (base class للإعدادات)
├── database.py        ← Base, get_db(), init_db(), get_engine()
├── security.py         ← JWT, bcrypt, sanitize, security headers
├── correlation.py      ← CorrelationMiddleware (X-Request-ID)
├── cache.py            ← get_cache/set_cache/rate_limit (Redis + in-memory fallback)
├── errors.py           ← APIError, ErrorCode, ErrorHandler, setup_error_handlers
├── health.py           ← build_health_router() — /health, /health/ready, /health/live
├── logging_setup.py    ← setup_logging(settings), get_logger()
├── middleware.py        ← SecurityHeadersMiddleware, RequestTimingMiddleware
├── sentry.py            ← setup_sentry(), capture_exception(), set_user_context()
├── whatsapp.py          ← send_whatsapp_message(), send_whatsapp(), notify_admin()
├── email_service.py     ← send_email(), send_password_reset_email() (SendGrid, اختياري)
├── reports.py           ← ReportBuilder — PDF (جدول/إيصال/إيصال حراري) + Excel
├── worker.py            ← make_celery() + CoreTask (auto-retry, structured logging)
├── models/
│   ├── user.py          ← User, RefreshToken, TokenBlacklist, UserRole
│   └── mixins.py        ← TimestampMixin, SoftDeleteMixin
└── auth/
    ├── repository.py    ← BaseRepository, UserRepository
    ├── service.py        ← AuthService (login lockout, JWT, refresh rotation, 2FA, password reset)
    └── router.py         ← build_auth_router() — /login /register /refresh /logout /2fa/* /password-reset/*
```

**اتأكد منه live (2026-07-03)**: بيئة Python نضيفة تمامًا (venv جديد، `pip install -r
requirements.txt` من غير ما `wego-core` يكون متثبّت خالص) — 753 اختبار عدّوا، السيرفر اشتغل، تسجيل
دخول حقيقي، `GET /auth/me`، `POST /2fa/setup` (pyotp)، وتوليد PDF حقيقي (reportlab + إعادة تشكيل
عربي) كلهم اشتغلوا صح. مفيش أي `import wego_core` باقي في أي كود حقيقي في المشروع.

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
- تأثير على Tests (هل 753 tests لا تزال تعدي؟)

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
☐ Permissions صحيحة (role guard على المستوى المناسب)
☐ PII مشفّرة
☐ Error handling كامل
☐ لا N+1 queries
☐ pytest tests/ -q لا يزال يعطي 753 passed
☐ alembic upgrade head يعمل بدون errors
```

---

## § 8 — Security Rules

الأمان غير قابل للتفاوض في هذا المشروع (بيانات ضيوف حقيقيين):

- كل endpoint حساس: `Depends(get_role_user(...))` بالمستوى المناسب
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
// - useAuthStore لكل قرار routing/visibility
// - لا hardcode للـ business rules في الـ UI
```

---

## § 11 — الوضع الحالي والمشاكل المعلّقة

> **المرجع الحقيقي لحالة المشروع لحظة بلحظة هو `/home/wego/projects/resort-os/PROJECT_STATUS.md`**
> — الملف ده (CLAUDE.md) بيوثّق القواعد والمعمارية الثابتة، مش الحالة اليومية المتغيرة.

### ✅ مكتمل
- 14 module (models/schemas/crud/services/router)، **كلهم دايمًا شغالين — مفيش نظام تفعيل/تعطيل** (§4)
- Domain engines: HR (راتب مصري)، Beach، Timeshare، Discount، Folio
- Double-entry accounting (Journal/Account/Period) + financial reports (trial balance، income
  statement، balance sheet)
- Offline POS، KDS WebSocket + شاشات منفصلة حقيقية لكل محطة (hot/grill/cold/bar/dessert)، QR menu،
  ETA e-invoice
- POS Money Count (عدّ الكاش بالفئة عند قفل الوردية، مع تفاصيل محفوظة للتدقيق)
- HR self-service كامل (`/hr/me/*`): بروفايل، حضور/انصراف (punch-in/out)، طلب إجازة، قسائم راتب
- دفتر يومية بعملة أجنبية فعليًا (دالة مشتركة `post_simple_revenue_journal`)، Audit Log موسّع (تغيير
  راتب/قفل فترة)، ربط CRM (`customer_id`) بمطعم/كافيه/شاطئ/PMS مع تحديث `total_spent` أوتوماتيك،
  "الدفع على حساب الغرفة" (Charge to Room) شغال فعليًا، تنبيهات واتساب حقيقية (مش TODO) في كل Celery
  tasks، ملاحظات تسليم الوردية، لوحة أداء الموظفين (`GET /hr/leaderboard`)، WebSocket لحظي حقيقي
  للـ KDS بإعادة اتصال تلقائي، 23 شاشة فرونت إند بتستخدم الـ `api` client المشترك (auto-logout شغال)
- **الاستقلالية الكاملة عن wego_core** (§6) + **نسخ احتياطي حقيقي للداتابيز** (`scripts/backup_db.sh`
  + `scripts/restore_db.sh` + systemd timer، اتأكد منه live بدورة backup→restore→مقارنة بيانات كاملة)
- 753 tests
- Frontend موحّد: `el-kheima` مع role-based routing، 3 layouts، مفيش module guard (اتشال)

### 🔴 حرجة (تمنع VPS deployment)
1. ~~`wego-core` editable local path~~ — **اتحل بالكامل 2026-07-03**: resort-os بقى مستقل 100%، مفيش
   أي اعتماد على `wego_core` خالص (راجع §6). اتأكد live ببيئة Python نضيفة تمامًا (`wego-core` مش
   متثبّت فيها أصلاً) — 753 اختبار عدّوا، سيرفر حقيقي اشتغل، تسجيل دخول + 2FA + توليد PDF كلهم اشتغلوا.
2. ~~Apps قديمة (admin/pos/kds/ops/waiter/portal) لا تزال في workspace~~ — **تم الحذف 2026-07-01**
   بعد التأكد الفعلي (browser walkthrough حقيقي بـ Playwright، مش curl بس) من إن `el-kheima` بيغطي كل الـ 6
   apps القديمة صح: login → role-based home صحيح، nav بيتفلتر حسب role، direct URL لـ route محمي
   بيعمل redirect مش render-then-403. تفاصيل كاملة في memory `project_resort_os.md`.

**مفيش حاجة حرجة متبقية تمنع النشر تقنيًا** — الباقي الوحيد هو تجربة فعلية على سيرفر حقيقي (مستنيين
IP + SSH access، شوف `PROJECT_STATUS.md`).

### 🟡 ناقصة للإنتاج الحقيقي
3. `localStorage` token → `httpOnly cookie`
4. باقي شاشات الفرونت إند غير الأساسية (`qr`/`public`، من غير تسجيل دخول) — الشاشات اللي محتاجة auth
   حقيقي (`el-kheima`) بقت كلها على الـ `api` client المشترك (23 ملف، 2026-07-03).
5. **Backups** — `scripts/backup_db.sh` + `scripts/restore_db.sh` + systemd timer اتعملوا واتأكد منهم
   live (2026-07-03: backup حقيقي، restore في DB منفصلة، مقارنة row counts طابقت بالظبط، safety guard
   ضد استرجاع غلط اتأكد منه) — **لسه محتاج يتفعّل فعليًا على السيرفر الحقيقي** لما يبقى موجود (مش
   مجرد كود جاهز، لازم `systemctl enable --now` فعلي + تأكيد أول تشغيل تلقائي).

### 🟢 تحسينات مستقبلية
6. تكرار كود ترحيل الإيرادات — اتحلّ جزئيًا (دالة مشتركة موجودة ومستخدمة في الـ 6 موديولات)، بس لسه
   مفيش معاملة حقيقية live بعملة غير الجنيه (المسار مجرّب بالتست بس).
7. Screen-level permissions (CanShow/CanAdd/CanEdit/CanDelete) — فيه أساس (`UserPermission`) بس مش
   كامل التغطية.
8. Auto-posting (كل فاتورة → journal entry تلقائي) خارج المسارات اللي بتعمل كده أصلاً.

---

## § 12 — Coverage الحالي (يحتاج attention)

آخر قياس فعلي (2026-07-02، `pytest --cov=app --cov-report=term-missing`) — **79% إجمالي**. أضعف
الـ routers (كل الأرقام دي `api/router.py` تحديدًا، مش الموديول كله):

```
analytics/api/router.py    30%  ← أولوية قصوى
hub/api/router.py          38%
core/api/router.py         41%
maintenance/api/router.py  43%
crm/api/router.py          51%
inventory/api/router.py    51%
```
قبل أي feature جديد في هذه الـ modules، أضف HTTP-level tests أولاً. الأرقام دي بتتغيّر مع كل تست
جديد — شغّل الأمر بنفسك لو محتاج رقم حالي بدل ما تصدّق اللي هنا.

---

## § 13 — تشغيل المشروع

```bash
# Backend
./start.sh                        # كل حاجة
./start.sh --no-frontend          # backend فقط
./start.sh --apps="el-kheima qr"  # frontend محدد

# Tests (لا تكمل أي task قبل ما 753 test تعدي)
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
❌ لا تكسر 753 test
```

---

*آخر تحديث: 2026-07-03*
*المشروع يستخدم: github.com/wego2388/Resort-OS · FastAPI 0.115 · SQLAlchemy 2.0 · Pydantic v2 · Vue 3.4 · pnpm*
