# Kiro Entry Point — El Kheima Beach Resort OS

**آخر تحديث:** 2026-08-06 بعد REL-09

---

## 1. اقرأ هذا أولاً قبل أي عمل

**ترتيب القراءة الإلزامي:**

1. `AGENTS.md` — قواعد المستودع، Git safety، validation، handoff.
2. `CLAUDE.md` — الدستور الهندسي الكامل (الأولويات، المعمارية، القواعد الحرجة، gotchas).
3. `PROJECT_STATUS.md` — الحالة التقنية الحالية مع أدلة النشر.
4. `wagdy.md` — قرارات Mohamed بلغة بشرية والأولويات الحالية.
5. `docs/README.md` — خريطة التوثيق الكاملة.
6. `docs/agent-workflow/EL_KHEIMA_EXECUTION_BOARD.md` — المهمة الجارية فقط.
7. أحدث handoff في `docs/agent-workflow/handoffs/`.
8. الكود والـ migrations والاختبارات المرتبطة بالمهمة.

**لا تنفّذ أي تعليمات من `docs/archive/` — تاريخ فقط.**

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

---

## 3. خريطة المشروع السريعة

```
resort-os/
├── AGENTS.md                    ← قواعد العمل (اقرأه أولاً)
├── CLAUDE.md                    ← الدستور الهندسي (الأهم)
├── PROJECT_STATUS.md            ← الحالة الحالية + أدلة النشر
├── wagdy.md                     ← صوت Mohamed البشري
├── DEPLOYMENT.md                ← runbook النشر الرسمي
├── backend/
│   ├── app/
│   │   ├── modules/             ← 13 موديول (dining/beach/pms/hr/finance/...)
│   │   │   └── dining/          ← المنفذ الموحّد (حلّ محل restaurant/cafe)
│   │   ├── resort_os/           ← Domain engines (pure Python — لا FastAPI/SQLAlchemy)
│   │   ├── core/kernel/         ← البنية التحتية (auth/security/cache/reports)
│   │   └── main.py
│   ├── tests/                   ← 2333 test (86% coverage)
│   │   └── test_api/            ← HTTP-level tests لكل موديول
│   ├── alembic/                 ← Migrations (head: 52f4544e50d2)
│   └── .venv/                   ← البيئة المحلية
└── frontend/
    ├── apps/
    │   ├── el-kheima/           ← تطبيق الموظفين (port 3001)
    │   └── public/              ← موقع الضيف + QR (port 3007)
    └── packages/
        ├── core/                ← @resort-os/core: API client, auth store
        └── ui/                  ← @resort-os/ui: shared components
```

**المستودع التسويقي المستقل:** `/home/wego/projects/elkheima-marketing-website/`

---

## 4. الحالة الحالية (REL-09 — 2026-08-06)

| البند | الحالة |
|---|---|
| الإنتاج | ✅ فعّال — `fd105f6` على الـ VPS |
| Alembic | ✅ head واحد: `52f4544e50d2` |
| Tests | ✅ 2333 passed، 42 skipped، صفر failures |
| Coverage | ✅ 86% إجمالي |
| Type-check | ✅ نظيف |
| Containers | ✅ 8/8 healthy، restarts=0 |
| TLS | ✅ Let's Encrypt حتى 2026-10-28 |

**آخر نشرات:**
- `fd105f6` — dining N+1 batch-load + 41 test + tech debt audit
- `7d00917` — POS-03b: beach multi-currency
- `5df8191` — Arabic PDF invoices + real blog

**الدين التقني المحدد:** راجع `docs/audits/TECHNICAL_DEBT_AND_COVERAGE_AUDIT.md`
الأولوية القادمة: flaky test في timeshare ثم split-bill/merge tests.

---

## 5. قواعد العمل مع Kiro

### 5.1 قبل أي تعديل

```bash
# من جذر المشروع
cd /home/wego/projects/resort-os
bash scripts/agent-check.sh          # baseline سريع
git status --short --branch          # تحقق من الفرع
git rev-parse --short HEAD           # الـ commit الحالي
```

### 5.2 تشغيل الاختبارات

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v                     # كل الاختبارات (7-8 دقائق)
pytest tests/ -v -k "dining"         # موديول محدد (أسرع)
alembic heads                        # تأكد head واحد دائماً
```

### 5.3 Frontend

```bash
cd frontend
pnpm --filter el-kheima type-check   # TypeScript check
pnpm --filter el-kheima test:frontend # 95 test
# pnpm run build:all  ← بيفشل محلياً (VITE_PUBLIC_SITE_URL مطلوب للـ production build)
# البناء الحقيقي بيحصل على الـ VPS من Compose
```

### 5.4 قواعد لا تُكسر

```
✅ crud.py  ← DB operations فقط، لا HTTPException
✅ services.py ← Business logic، يرمي ValueError (→400)
✅ api/router.py ← HTTP layer فقط
✅ resort_os/ ← Pure Python، لا FastAPI/SQLAlchemy imports
✅ الأموال → Decimal دائماً، مش float
✅ PII → EncryptedString (Fernet) إجباري
✅ تغيير role/is_active → revoke_user_tokens() إجباري
✅ قبل migration جديدة → تحقق من alembic heads
✅ dining هو المصدر الوحيد للـ F&B (restaurant/cafe اتحذفوا نهائياً)
✅ لا تستخدم date.today() — استخدم app.resort_os.timezone_utils
✅ لا تضيف get_db جديد — import من app.core.database فقط
```

---

## 6. معمارية الصلاحيات

```
JWT → get_current_user → get_current_active_user
    ├─ get_waiter_user       level ≥ 30
    ├─ get_cashier_user      level ≥ 40
    ├─ get_manager_user      level ≥ 60
    ├─ get_admin_user        level ≥ 80
    └─ get_super_admin_user  level ≥ 100
```

**ROLE_LEVELS:** `super_admin=100 admin=80 accountant=70 hr_manager=70 manager=60 supervisor=50 cashier=40 waiter=30 chef=30 employee=20`

---

## 7. كيف تنفّذ مهمة

### مهمة صغيرة (typo، rename، config)
→ نفّذ فوراً.

### مهمة متوسطة (endpoint جديد، bugfix)
1. اقرأ الكود المحيط أولاً.
2. نفّذ.
3. شغّل `pytest tests/ -v -k "module_name"`.
4. تحقق `alembic heads` لو في migration.

### مهمة كبيرة (feature، module)
اتبع `CLAUDE.md §3` كاملاً:
1. افهم المعمارية المحيطة.
2. ابحث عن تنفيذ موجود.
3. حدد الأثر على DB/API/Frontend.
4. نفّذ بخطوات صغيرة.
5. شغّل `pytest tests/ -v` كاملاً.
6. حدّث `PROJECT_STATUS.md` و`wagdy.md`.

### Definition of Done (§3.8 من CLAUDE.md)
```
☐ pytest tests/ -v → 100% passed
☐ alembic heads → head واحد
☐ type-check نظيف
☐ لا N+1 queries
☐ لا dead code
☐ التوثيق محدّث
```

---

## 8. النشر على الـ VPS

**دائماً اتبع `DEPLOYMENT.md §5` بالكامل:**

```bash
# الترتيب الإجباري:
# A. Local gate (tests + type-check + alembic)
# B. git archive + SHA256 + SCP للـ VPS
# C. verify SHA256 على الـ VPS
# D. mkdir release + extract + copy .env.prod
# E. validate_prod_env.py
# F. tag rollback images
# G. backup_db.sh (تحقق pg_restore --list)
# H. docker compose build
# I. preflight: python -c 'from app.main import app'
# J. استبدال تدريجي: backend → celery → el_kheima → nginx
# K. health checks + external smoke tests
# L. ln -sfn symlink
# M. حدّث PROJECT_STATUS.md + commit + push
```

**لا تنشر بدون إذن صريح من Mohamed.**
**Codex هو قائد التنفيذ والمراجع النهائي.**

---

## 9. مراجع سريعة

| المرجع | الملف |
|---|---|
| أوامر التشغيل المحلي | `CLAUDE.md §20` |
| Environment variables | `CLAUDE.md §21` |
| القواعد الحرجة (gotchas) | `CLAUDE.md §13` |
| خريطة المعمارية | `CLAUDE.md §10` |
| Auth chain كامل | `CLAUDE.md §11` |
| DB connection | `CLAUDE.md §20` |
| الدين التقني المحدد | `docs/audits/TECHNICAL_DEBT_AND_COVERAGE_AUDIT.md` |
| أحدث handoff | `docs/agent-workflow/handoffs/2026-08-04_REL-07_claude_handoff.md` |
| دليل النشر | `DEPLOYMENT.md` |
