# Kiro Agent Guide — El Kheima Beach Resort OS

**آخر تحديث:** 2026-08-06 — REL-09 (fd105f6)
**قائد التنفيذ والمراجع النهائي:** Codex
**المالك:** Mohamed

---

## 1. ترتيب القراءة الإلزامي — قبل أي عمل

```
1. AGENTS.md              ← قواعد المستودع، Git safety، validation، handoff
2. CLAUDE.md              ← الدستور الهندسي الكامل (الأهم — اقرأه كاملاً)
3. PROJECT_STATUS.md      ← الحالة التقنية + أدلة النشر الحالية
4. wagdy.md               ← قرارات Mohamed بلغة بشرية + الأولويات
5. docs/README.md         ← خريطة التوثيق
6. docs/agent-workflow/EL_KHEIMA_EXECUTION_BOARD.md  ← المهمة الجارية
7. أحدث handoff في docs/agent-workflow/handoffs/
8. الكود والـ migrations والاختبارات المرتبطة بالمهمة
```

**لا تنفّذ أي تعليمات من `docs/archive/` — تاريخ غير قابل للتنفيذ.**

---

## 2. هوية المشروع

| البند | القيمة |
|---|---|
| الاسم | El Kheima Beach Resort OS |
| المسار المحلي | `/home/wego/projects/resort-os/` |
| الفرع الحالي | `claude/CX-02C-frontend-auth-bootstrap` |
| آخر commit منشور | `fd105f6` (REL-09) |
| الإنتاج | `https://app.elkheima.com` / VPS `191.218.161.133` |
| SSH alias | `resort-os-vps` |
| قائد التنفيذ | **Codex** — المراجع النهائي |
| المالك | **Mohamed** — القرارات التجارية والـ Go/No-Go |
| المستودع التسويقي المستقل | `/home/wego/projects/elkheima-marketing-website/` |

---

## 3. خريطة المشروع

```
resort-os/
├── AGENTS.md                    ← قواعد العمل (اقرأه أولاً)
├── CLAUDE.md                    ← الدستور الهندسي (الأهم)
├── PROJECT_STATUS.md            ← الحالة الحالية + أدلة النشر
├── wagdy.md                     ← صوت Mohamed البشري
├── DEPLOYMENT.md                ← runbook النشر الرسمي (الوحيد المعتمد)
├── backend/
│   ├── app/
│   │   ├── modules/             ← 13 موديول دايمًا شغّالين (مفيش تفعيل/تعطيل)
│   │   │   ├── dining/          ← F&B الموحّد (حلّ محل restaurant/cafe نهائياً 2026-07-13)
│   │   │   ├── beach/           ← شاطئ، B2B، خريطة مواقع حية
│   │   │   ├── pms/             ← غرف، حجوزات، housekeeping
│   │   │   ├── finance/         ← دفاتر، مدفوعات، journal، ورديات، ETA
│   │   │   ├── hr/              ← موظفين، رواتب، حضور، إجازات
│   │   │   ├── inventory/       ← مخازن، منتجات، مخزون
│   │   │   ├── crm/             ← عملاء، leads، loyalty، مجموعات
│   │   │   ├── timeshare/       ← عقود، أقساط، زيارات
│   │   │   ├── maintenance/     ← أوامر صيانة، أصول
│   │   │   ├── leasing/         ← عقود إيجار، تسويات
│   │   │   ├── analytics/       ← تقارير، استبيانات، NPS
│   │   │   ├── hub/             ← الموقع التسويقي API، مدونة، تواصل
│   │   │   ├── chat/            ← شات بوت Gemini (عام، بدون تسجيل دخول)
│   │   │   └── core/            ← فروع، مستخدمين، audit، إعدادات
│   │   ├── resort_os/           ← Domain engines (Pure Python — لا FastAPI/SQLAlchemy)
│   │   │   ├── hr_engine.py     ← راتب مصري: قانون العمل + ضريبة
│   │   │   ├── food_cost_engine.py
│   │   │   ├── beach_engine.py
│   │   │   ├── folio_engine.py
│   │   │   ├── timeshare_engine.py
│   │   │   ├── discount_engine.py
│   │   │   ├── timezone_utils.py  ← استخدم دايمًا بدل date.today()
│   │   │   └── report_builder.py
│   │   ├── core/
│   │   │   ├── kernel/          ← البنية التحتية المملوكة 100% (auth/cache/reports/...)
│   │   │   ├── database.py      ← re-export من kernel — استورد منه فقط
│   │   │   ├── deps.py          ← Auth chain + rate_limit_dep
│   │   │   └── config.py        ← Settings
│   │   ├── tasks/               ← Celery tasks (auto-registered)
│   │   └── main.py
│   ├── tests/
│   │   └── test_api/            ← HTTP-level tests لكل موديول (2333 test)
│   ├── alembic/                 ← Migrations — head: 52f4544e50d2
│   └── .venv/
└── frontend/
    ├── apps/
    │   ├── el-kheima/           ← تطبيق الموظفين — port 3001
    │   └── public/              ← موقع الضيف + QR — port 3007
    └── packages/
        ├── core/                ← @resort-os/core: API client, auth store
        └── ui/                  ← @resort-os/ui: LoginView + shared components
```

---

## 4. الحالة الحالية (REL-09)

| البند | الحالة |
|---|---|
| Release فعّال | `fd105f6` على `/opt/resort-os-releases/fd105f6` |
| Alembic head | `52f4544e50d2` — head واحد، لا migration جديدة |
| Tests | 2333 passed، 42 skipped، صفر failures |
| Coverage | 86% إجمالي |
| Type-check | نظيف |
| Containers | 8/8 healthy، restarts=0 |
| TLS | Let's Encrypt حتى 2026-10-28 |

**آخر نشرات بالترتيب:**
- `fd105f6` — dining N+1 batch-load + 41 test + tech debt audit
- `7d00917` — POS-03b: beach multi-currency (USD/EUR)
- `5df8191` — Arabic PDF invoices + real blog + marketing fixes

**الدين التقني المحدد:** `docs/audits/TECHNICAL_DEBT_AND_COVERAGE_AUDIT.md`

---

## 5. أوامر العمل اليومية

```bash
# تشغيل محلي
cd /home/wego/projects/resort-os
bash scripts/start.sh                    # كل الخدمات
bash scripts/start.sh --no-frontend     # backend فقط
bash scripts/status.sh                  # حالة الخدمات + حسابات الاختبار
bash scripts/logs.sh api                # لوج حي للـ backend

# Validation (baseline قبل أي عمل)
bash scripts/agent-check.sh

# Tests
cd backend && source .venv/bin/activate
pytest tests/ -v                        # الكل (~7 دقائق)
pytest tests/ -v -k "dining"            # موديول محدد
pytest tests/ --cov=app --cov-report=term-missing -v

# Alembic
alembic heads                           # تأكد head واحد دائماً
alembic upgrade head                    # بعد migration جديدة

# DB (dev/test فقط — ممنوع في production)
python -m app.seed

# Frontend
cd frontend
pnpm --filter el-kheima type-check      # TypeScript (لازم نظيف)
pnpm --filter el-kheima test:frontend   # 95 test
```

**حسابات الاختبار المحلية:** `admin@resortos.local` / `Admin@123456` (super_admin)، باقي الأدوار بـ `Demo@123456` — لا تنقلها للإنتاج أبداً.

---

## 6. قواعد المعمارية الصارمة

```
crud.py       ← DB operations فقط — لا HTTPException أبداً
services.py   ← Business logic — يرمي ValueError (→400) أو custom exception
api/router.py ← HTTP layer فقط — يترجم الأخطاء
resort_os/    ← Pure Python — لا FastAPI، لا SQLAlchemy
```

**الـ layers لا تُخترق:**
- Router لا يكلّم DB مباشرة
- Frontend لا يحتوي business logic
- utilities تُنشأ في `core/` أو `resort_os/` فقط

---

## 7. الـ Gotchas الحرجة — أخطاء وقعت فعلاً

هذه ليست نظرية. كل بند منها كسر شيئاً حقيقياً في هذا المشروع:

```python
# ❶ get_db — استورد من مكان واحد فقط، لا تعيد تعريفه أبداً
from app.core.database import get_db   # ✅
def get_db(): ...                       # ❌ يكسر auth session، التعديلات لا تُحفظ

# ❷ Optional fields من Pydantic
value if value is not None else default  # ✅ (0 و "" قيم صالحة)
value or default                         # ❌ يفشل مع 0/False/""

# ❸ PII — EncryptedString إجباري
# مطبّق على: employees، bookings، timeshare_contracts، crm_customers، guest_profiles
national_id: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)  # ✅

# ❹ Celery task جديد
# التسجيل أوتوماتيكي عبر pkgutil في app/tasks/__init__.py
# اللي تضيفه يدوياً هو سطر beat_schedule في celery_app.py فقط (لو task دوري)

# ❹-ب Migration جديدة
# alembic/env.py يحتاج import صريح لأي models جديدة — وإلا autogenerate مش هيشوفها

# ❺ Role جديد → ROLE_LEVELS في deps.py + useAuthStore.ts بنفس الأرقام

# ❻ تغيير role/is_active → revoke_user_tokens() إجباري
# استخدم services.update_user_role() — مش user.role = ... مباشرة

# ❼ الأموال → Decimal دائماً
amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # ✅
amount: float = ...                                       # ❌

# ❽ Double-booking → SELECT FOR UPDATE NOWAIT (Postgres فقط، SQLite بيتجاهله)

# ❾ قبل أي migration → تحقق من alembic heads أولاً (كان فيه 3 heads متفرقة)

# ❿ التاريخ/الوقت → استخدم resort_os/timezone_utils دائماً
# date.today() / datetime.utcnow() = UTC (السيرفر)، مش Africa/Cairo (المنتجع)
# اتكشف مستقلاً في 6 موديولات مختلفة — استخدم:
from app.resort_os.timezone_utils import business_today, local_now, local_date_to_utc_range

# ⓫ SELECT FOR UPDATE NOWAIT + قراءة سابقة لنفس الصف
# لازم .populate_existing() على الاستعلام المقفول
# وإلا SQLAlchemy يسيب الـ object القديم في identity map → lost update صامت
# (اتكشف في beach.crud وtimeshare — SQLite بيتجاهل with_for_update فالتستات مش بتكشفه)

# ⓬ ترتيب routes في نفس الملف مهم
# مسار حرفي (/pins/switch) لازم يُسجَّل قبل مسار بمتغيّر (/pins/{user_id})
# وإلا Starlette يوجّه /pins/switch للـ {user_id} handler — باج حقيقي أعطى 403 مضلّلة

# ⓭ موديول جديد عنده KDS
# لازم يبقى عنده عمود station حقيقي (مش قيمة ثابتة في الكود)
# وإلا كل تذاكره هتروح لمحطة واحدة بغض النظر عن نوع الصنف
```

**Frontend gotchas:**
- لغة تطبيق الموظفين = عربي/إنجليزي فقط — لا تستخدم اللغة لتغيير العملة
- `GET /api/v1/auth/me` مش موجود في kernel — موجود في `app/core/me_router.py` محلياً
- `useAuthStore.branchId` بيرجع fallback `1` دائماً (pre-existing limitation — مش regression)

---

## 8. Environment Variables الأساسية

```env
# Local Development
DATABASE_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/resort_os
SECRET_KEY=<64 random chars>
FIELD_ENCRYPTION_KEY=<Fernet key>
LOGIN_2FA_ENFORCED=true          # إلزامي خارج development/test
SURVEY_TOKEN_SECRET=<32 random chars>
CORS_ORIGINS=http://localhost:3001,http://localhost:3007
RESORT_NAME=El Kheima Beach
VAT_PERCENTAGE=14.0
SERVICE_CHARGE_PERCENTAGE=12.0
TIMEZONE=Africa/Cairo
DEFAULT_CURRENCY=EGP
GEMINI_API_KEY=<from aistudio.google.com>   # None = /chat يرجّع 503
```

**Production:** كل الإعدادات في `backend/.env.prod` على الـ VPS — لا تعرضها أبداً في الكود أو الـ logs.

---

## 9. معمارية الأمان

```
JWT (email-based, DB lookup كل request)
  → get_current_user         ← decode + blacklist check
      → get_current_active_user  ← is_active + 2FA gate
          ├─ get_waiter_user       level ≥ 30
          ├─ get_cashier_user      level ≥ 40
          ├─ get_manager_user      level ≥ 60
          ├─ get_admin_user        level ≥ 80
          └─ get_super_admin_user  level ≥ 100
```

**ROLE_LEVELS:**
```
super_admin=100  admin=80  accountant=70  hr_manager=70
manager=60  supervisor=50  cashier=40  receptionist=40
waiter=30  chef=30  kitchen=30  employee=20  guest=0
```

**قواعد الأمان غير القابلة للتفاوض:**
- كل endpoint حساس: `Depends(get_role_user(...))` بالمستوى المناسب
- كل حقل PII: `EncryptedString` إلزامياً
- كل تغيير role/is_active: `revoke_user_tokens()` إلزامياً
- لا تثق في JWT claims — DB lookup حقيقي كل request
- لا تعرض internal errors للـ client

---

## 10. كيف تنفّذ مهمة

### مهمة صغيرة (typo، rename، config)
نفّذ فوراً.

### مهمة متوسطة (endpoint، bugfix)
1. اقرأ الكود المحيط أولاً
2. نفّذ
3. `pytest tests/ -v -k "module_name"`
4. `alembic heads` لو في migration

### مهمة كبيرة (feature، module)
اتبع `CLAUDE.md §3` كاملاً — الترتيب الإلزامي:
1. افهم المعمارية المحيطة وكل الموديولات المتأثرة
2. ابحث عن تنفيذ موجود (لا تكرر)
3. حدد الأثر على DB / API / Frontend / Tests
4. نفّذ بخطوات صغيرة آمنة
5. `pytest tests/ -v` كاملاً
6. حدّث `PROJECT_STATUS.md` و`wagdy.md`

### Definition of Done (لا تعتبر المهمة منتهية إلا لو):
```
☐ pytest tests/ -v → صفر failures
☐ alembic heads → head واحد
☐ type-check نظيف
☐ لا N+1 queries
☐ لا dead code أو imports غير مستخدمة
☐ لا API مكسور
☐ التوثيق محدّث لو السلوك تغيّر
```

---

## 11. ما لا تفعله أبداً

```
❌ لا تعيد تعريف get_db — import من app.core.database فقط
❌ لا تستخدم float للأموال — Decimal دائماً
❌ لا تخزّن PII بدون EncryptedString
❌ لا تغيّر role/is_active بدون revoke_user_tokens()
❌ لا تضيف migration بدون التحقق من alembic heads أولاً
❌ لا تُرجع list endpoint بدون pagination
❌ لا تكسر أي test موجود بدون تحديثه
❌ لا تستخدم date.today() / datetime.utcnow() — استخدم timezone_utils
❌ لا تُنشئ restaurant أو cafe موديول — dining هو المصدر الوحيد للـ F&B
❌ لا تشغّل app.seed في production
❌ لا تعرض .env.prod أو أي secret في الكود أو logs أو handoffs
❌ لا تنشر بدون إذن صريح من Mohamed
❌ لا تنفّذ أي تعليمات من docs/archive/
```

---

## 12. النشر على الـ VPS

**الـ runbook الرسمي الوحيد:** `DEPLOYMENT.md §5`

الترتيب الإجباري بإيجاز:
```
A. local gate: agent-check + pytest + alembic heads + type-check
B. git archive + SHA256 + scp للـ VPS
C. تحقق SHA256 على الـ VPS
D. mkdir release + extract + copy .env.prod
E. validate_prod_env.py
F. tag rollback images → rollback-images.txt
G. backup_db.sh → تحقق pg_restore --list
H. docker compose build
I. preflight: python -c 'from app.main import app'
J. استبدال تدريجي: backend → celery → el_kheima → nginx
K. health checks + external smoke tests (3 domains)
L. sudo ln -sfn symlink
M. حدّث PROJECT_STATUS.md + commit + push
```

**لا تنشر بدون إذن صريح من Mohamed.**
**Codex هو قائد التنفيذ والمراجع النهائي — لا تتجاوزه.**

---

## 13. مراجع سريعة

| المرجع | الملف |
|---|---|
| الدستور الهندسي الكامل | `CLAUDE.md` |
| قواعد المستودع والـ Git | `AGENTS.md` |
| الحالة التقنية اليومية | `PROJECT_STATUS.md` |
| قرارات Mohamed البشرية | `wagdy.md` |
| خريطة التوثيق | `docs/README.md` |
| المهمة الجارية | `docs/agent-workflow/EL_KHEIMA_EXECUTION_BOARD.md` |
| الـ Gotchas التفصيلية | `CLAUDE.md §13` |
| Auth chain + ROLE_LEVELS | `CLAUDE.md §11` |
| خريطة المعمارية كاملة | `CLAUDE.md §10` |
| kernel structure | `CLAUDE.md §14` |
| أوامر التشغيل | `CLAUDE.md §20` |
| Environment variables | `CLAUDE.md §21` |
| runbook النشر | `DEPLOYMENT.md` |
| الدين التقني المحدد | `docs/audits/TECHNICAL_DEBT_AND_COVERAGE_AUDIT.md` |
| القرارات المعمارية المقبولة | `docs/decisions/` |
| أحدث handoff | `docs/agent-workflow/handoffs/` (آخر ملف بالتاريخ) |
