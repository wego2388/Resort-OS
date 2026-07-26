# El Kheima Beach Resort OS — Agent Instructions

These instructions apply to the entire repository. They are the shared entry
point for Codex and any other engineering agent. Claude must also read
`CLAUDE.md` in full.

## 1. Read order and authority

Before changing code, read in this order:

1. The user's current request and any approved task brief.
2. This file.
3. `CLAUDE.md` in full for the engineering charter and project-specific rules.
4. The beginning and newest relevant dated sections of `PROJECT_STATUS.md`.
5. Task-specific accepted decisions under `docs/decisions/`.
6. `wagdy.md` for Mohamed's current plain-language priorities, decisions,
   risks, and project view.
7. The relevant code, migrations, tests, and runtime configuration.

Authority, from highest to lowest:

1. Explicit current user decisions.
2. An approved task brief or accepted decision record.
3. This file and the stable rules in `CLAUDE.md`.
4. Current code, tests, migrations, and configuration as evidence of existing
   behavior.
5. `wagdy.md` for current human priorities and explanation (not as proof of
   implementation).
6. `PROJECT_STATUS.md` as a dated operational record.
7. Historical plans such as `MASTER_TODO.md`, `FRONTEND_GAPS.md`,
   `RESORT_OS_FULL_ANALYSIS.md`, and old sections of status documents.

Historical plans are context, not an automatically approved backlog. If a
document conflicts with current code or a newer decision, report the conflict
instead of silently choosing one. Never trust a stored test count; collect or
run the tests relevant to the task.

## 2. Product facts that must remain consistent

- The exact brand spelling is **El Kheima Beach**.
- This is a single-resort operational system, with branch/outlet scoping where
  the existing data model supports it. Do not invent SaaS multi-tenancy.
- There are 13 active backend modules. `dining` is the only active food and
  beverage bounded context; do not recreate `restaurant` or `cafe` modules.
- The staff app is `frontend/apps/el-kheima` on development port 3001.
- The guest website is `frontend/apps/public` on development port 3007.
- The temporary Super Admin project cockpit is
  `frontend/apps/el-kheima/src/views/dev/ProjectCockpitView.vue` at
  `/admin/project-cockpit`. It is development-only, must remain absent from
  production builds, and uses dated curated data in
  `src/dev/projectCockpitData.ts` and
  `src/dev/projectCockpitExperienceData.ts`; it is not live telemetry and its
  local quality worksheet is not acceptance evidence. The current 360-degree
  audit and risk/dependency gates are in `docs/audits/`. When a material
  decision or phase status changes, update `wagdy.md` first and only then the
  affected snapshot entries with evidence.
- The accepted QR/guest-service product decisions are recorded in
  `docs/decisions/0001-qr-guest-service-mode.md`. That record is a decision,
  not proof that the current implementation already complies with it.
- The staff application is approved for complete Arabic/English operation as
  recorded in `docs/decisions/0002-staff-app-bilingual-mode.md`. This does not
  change the public application's independently configured locale list, and it
  is not proof that all current staff screens are translated.
- The approved super-admin authority and safety invariants are recorded in
  `docs/decisions/0003-super-admin-control-plane.md`. Full administrative
  authority never means bypassing financial integrity, audit immutability,
  secrets handling, or destructive-operation safeguards.
- The external 38-page development plan reviewed on 2026-07-17 is a quality
  charter, not authorization for a single repository-wide overhaul. Convert
  it into bounded tasks and use the actual repository commands and evidence.
- PMS/Finance room-revenue unification is intentionally deferred and must not
  be implemented as incidental work. It requires a dedicated design review
  with Mohamed, as documented in `CLAUDE.md` and `PROJECT_STATUS.md`.

## 3. Choose the correct working mode

- **Review/audit request:** inspect and report only. Do not edit files, create
  migrations, commit, or push.
- **Planning request:** establish evidence, root cause, scope, risks, expected
  files, acceptance criteria, and validation. Stop at the requested approval
  gate.
- **Implementation request:** implement only the approved phase. A broad
  product prompt is a charter until it has been converted into a bounded task
  brief.
- **Documentation-only request:** do not opportunistically refactor product
  code.

"Leave the code better" means safe, task-related cleanup. It does not authorize
unrelated rewrites, mass formatting, dependency upgrades, or backlog work.

## 4. Mandatory start checklist

1. Run `git status --short --branch`, `git branch --show-current`,
   `git rev-parse --short HEAD`, and `git worktree list`.
2. Preserve all user-owned changes. If relevant files are already modified,
   inspect the overlap and stop only if safe isolation is impossible.
3. Do not run `git pull` blindly. Fetch and inspect divergence first. This
   repository may have a local `main` intentionally ahead of `origin/main`.
4. If code will be changed while on `main` or `master`, create a focused branch
   or an explicitly based worktree before editing.
5. Search for an existing implementation before designing a replacement.
6. Read the nearest models, schemas, CRUD, services, routers, frontend callers,
   migrations, and tests for the workflow in scope.
7. State assumptions and identify business decisions that cannot safely be
   inferred.

Run `bash scripts/agent-check.sh` for a read-only local baseline.

## 5. Engineering guardrails

### Architecture

- Preserve the backend flow: router (HTTP) -> service (business rules) -> CRUD
  (persistence) -> model.
- Keep pure calculation engines in `backend/app/resort_os/` free of FastAPI and
  SQLAlchemy imports.
- Keep server state separate from local UI state and use the shared frontend
  packages before creating duplicate components or API clients.
- Prefer a practical modular monolith. Do not add a new architectural layer or
  service without concrete evidence that the current structure cannot support
  the task.

### Data and finance

- Use `Decimal`/`Numeric` for money; never binary floating point.
- Preserve reproducible historical prices and totals.
- Posted financial records are immutable in normal workflows; correct them by
  explicit reversal/replacement operations.
- Every financial mutation needs a clear transaction boundary, source
  reference, authorization, and audit trail.
- Use database constraints, idempotency, and row locking where concurrent
  operations can violate an invariant. Remember SQLAlchemy identity-map
  refresh requirements described in `CLAUDE.md`.
- Use `backend/app/resort_os/timezone_utils.py` for resort business dates and
  times. Follow the repository's existing UTC storage convention; do not start
  a blanket timestamp migration.

### Security and authorization

- Enforce authorization server-side using the existing role, permission, and
  policy-engine patterns. Frontend visibility is not authorization.
- Derive trusted branch, outlet, location, price, and ownership context on the
  server. Public clients must not select protected context by arbitrary IDs.
- Encrypt supported PII with the existing `EncryptedString` pattern.
- Never log secrets, passwords, tokens, card data, or unnecessary personal
  data.
- Sensitive actions need attributable audit events; do not create a parallel
  audit system.
- An active `super_admin` must retain complete application permission. Do not
  create explicit permission overrides for that role, permit routine
  self-demotion/self-deactivation, or allow the last active super admin to be
  removed. Enforce these invariants server-side and transactionally.
- Super-admin login and high-risk administration must follow Decision 0003's
  TOTP/step-up requirements. Frontend confirmation alone is not proof of recent
  authentication.

### Frontend localization and settings

- In `frontend/apps/el-kheima`, new staff-facing copy must be available in
  Arabic and English through the shared localization runtime. Do not add a
  forced global direction, hard-coded locale formatting, or unexplained
  left/right layout rules.
- Keep the staff locale allow-list separate from `frontend/apps/public`.
  Changing an employee's language must never change currency, stored prices,
  tax rules, or other resort configuration.
- Personal preferences, branch operational settings, global settings, and
  secrets are different scopes. Follow Decisions 0002 and 0003; do not extend
  an arbitrary free-form settings mechanism.

### Database and API compatibility

- Never delete migration history or edit an applied migration when a forward
  migration is safer.
- Check `alembic heads` before creating a migration. Preserve one head unless a
  deliberate merge migration is required.
- Do not apply destructive migrations or invalidate live identifiers without
  an impact and rollback plan.
- Preserve public APIs by default. If a contract must change, document affected
  callers, compatibility behavior, and migration steps.

### Scope and dependencies

- Do not add dependencies until existing capabilities have been checked and
  the dependency is justified in the task report.
- Do not modify generated files manually.
- Do not hide exceptions, weaken tests, skip failures without explanation, or
  claim production readiness from static inspection alone.

## 6. Git and collaboration safety

- Never use `git reset --hard`, `git clean -fd`, history rewriting, or blanket
  checkout commands.
- Do not use `git add .` as a checkpoint. Stage reviewed paths explicitly.
- Do not commit or push unless the user explicitly asks for it.
- One implementation task should have one owning worktree.
- To review Claude's uncommitted work, run Codex read-only from a second
  terminal in the **same worktree**. A separate worktree cannot see another
  worktree's uncommitted diff.
- Use separate worktrees only for genuinely independent tasks. Never let two
  agents edit the same files concurrently.

The detailed team workflow and reusable prompts are in
`docs/agent-workflow/`.

## 7. Validation contract

Use commands that actually exist in this repository:

```bash
# Always
git diff --check
git status --short --branch

# Backend
cd backend
.venv/bin/pytest tests/ -v
.venv/bin/alembic heads

# Frontend
cd frontend
pnpm run type-check:all
pnpm run build:all

# Deployment configuration
cd ..
docker compose config --quiet
docker compose -f docker-compose.prod.yml config --quiet
```

Run targeted tests during development and the full affected-layer checks at a
phase gate. Migration-related work also needs upgrade/rollback reasoning and a
real PostgreSQL check when concurrency or PostgreSQL-specific behavior matters.

`ruff` and `mypy` are not currently installed/configured as repository-wide
quality gates, and there is no configured frontend lint or automated frontend
test command. Do not report those checks as passed. If adding such tooling is a
task, introduce it separately with configuration, a clean baseline, and an
explicit dependency justification.

## 8. Migration Session — 2026-07-26 (Kiro Agent)

### ما الذي تغيّر في هذه الجلسة

#### الخلاصة
تم استبدال الموقع العام القديم (`frontend/apps/public`) بمشروع تسويقي جديد أكثر نضجًا (`/home/wego/projects/elkheima-marketing-website`)، مع الحفاظ الكامل على الـ backend بدون أي تعديل.

---

#### أولاً — ما أُزيل من resort-os

**`frontend/apps/public/` — أُرشف ولم يُحذف من التاريخ**
- المجلد مضغوط في: `backups/apps-public-archive-20260726_062054.tar.gz` (21MB)
- الاستعادة: `cd frontend && tar -xzf ../backups/apps-public-archive-20260726_062054.tar.gz`
- script `dev:public` حُذف من `frontend/package.json`
- الـ `apps/*` glob في `pnpm-workspace.yaml` لم يحتج تغييراً

**السبب:** الموقع الجديد يحتوي على كل ما كان في القديم وأكثر بكثير (i18n متقدم، PWA، SEO، صفحات أكثر، تصميم أفضل).

---

#### ثانياً — ما أُضيف لـ elkheima-marketing-website

المشروع في `/home/wego/projects/elkheima-marketing-website` — **مستقل تماماً عن الـ monorepo** (npm، ليس pnpm).

**ملفات جديدة:**

| الملف | الوظيفة |
|---|---|
| `src/apps/ops/QrOrder.vue` | نُقل من `apps/public/src/views/OrderView.vue` — يتكلم مع **dining module** (`/api/v1/dining/public`) بالكامل بدون أي تغيير في الـ endpoints أو الـ logic. فقط `axios` استُبدل بـ `client` من `@/api/client`. الـ template أُعيد تصميمه بتصميم Hub الداكن. |
| `src/apps/ops/GuestSurvey.vue` | نُقل من `apps/public/src/views/SurveyView.vue` — يتكلم مع `/api/v1/analytics/reviews/submit`. نفس التعديل فقط. |
| `Dockerfile` | Multi-stage build مستقل (node:20-slim → nginx:1.27-alpine). `VITE_API_URL` فارغ عمداً في production. |
| `nginx.spa.conf` | نسخة من `resort-os/frontend/nginx.spa.conf` — SPA fallback + proxy `/api/` → `backend:8005`. |

**تعديلات على ملفات موجودة:**

| الملف | التعديل |
|---|---|
| `src/router/routes/public.routes.ts` | أُضيف `/s/:token` و `/survey/:token` **خارج** `withLocalePrefix` عمداً — QR codes المطبوعة لا تحتوي locale prefix |
| `src/i18n/locales/ar.json` | أُضيف قسم `qr.*` كامل (38 مفتاح) |
| `src/i18n/locales/en.json` | نفس الـ keys بالإنجليزية |

---

#### ثالثاً — ما تغيّر في resort-os

**`docker-compose.prod.yml`**
- أُضيف service جديد `marketing_site` يبني من `/home/wego/projects/elkheima-marketing-website`
- `public_site` أُبقي مؤقتاً كـ fallback — **لا يصله traffic من nginx** — يُحذف بعد 48h من استقرار production

**`deploy/nginx/edge.conf`**
- `yourdomain.com` و `www.yourdomain.com` يُحوَّلان لـ `marketing_site:80` بدلاً من `public_site:80`
- `app.yourdomain.com` لم يتغير → `el_kheima:80`

**`scripts/start.sh`**
- `APPS="el-kheima public"` → `APPS="el-kheima"`
- حُذف `--apps=` flag
- أُضيفت ملاحظة: الموقع الجديد يُشغَّل بشكل مستقل على port 5174

**`scripts/stop.sh`**
- حُذف port 3007 من safety net

**`scripts/status.sh`**
- استُبدل `pid_status "public"` بـ curl check مباشر على `http://127.0.0.1:5174`

**`scripts/logs.sh`**
- حُذف `frontend-public.log` من الـ tail

---

#### رابعاً — ما لم يتغير خالص

- `backend/` — صفر تعديل
- `frontend/apps/el-kheima/` — صفر تعديل
- `frontend/packages/core/` و `packages/ui/` — صفر تعديل
- `docker-compose.yml` (dev) — صفر تعديل
- كل الـ backend API endpoints — صفر تعديل
- قاعدة البيانات والـ migrations — صفر تعديل

---

#### خامساً — نقاط حرجة يجب أن يعرفها أي agent يعمل بعد هذه الجلسة

**1. نظامان للمنيو — مختلفان تماماً:**
- `dining` module → `dining_items` / `dining_categories` / `dining_outlets` في الـ DB → يُستخدم في `/s/:token` (QrOrder.vue)
- `products` module (inventory) → `products` table → يُستخدم في `/hub` (DigitalHub.vue و DigitalMenu.vue)
- **لا تخلطهم** — كل واحد له endpoints ونظام سلة مستقل

**2. `/s/:token` flow لم يتغير منطقياً:**
```
QR code → /s/{token} → resolveGuestContext() →
GET /api/v1/public/service-location?token={token} →
POST /api/v1/public/guest-sessions →
GET /api/v1/dining/public/service-menu →
POST /api/v1/dining/public/orders
```
فقط التصميم البصري تغيّر (dark Hub theme بدلاً من light stone theme).

**3. `BeachCheckinView.vue` لم يُنقل عمداً:**
كان يستخدم `@resort-os/core` (monorepo package غير موجود في elkheima-marketing-website). القرار: هذا الروت (`/beach/checkin/:reservationId`) غير موجود في الموقع الجديد حالياً. لو احتجت تضيفه لاحقاً: انسخ `BeachCheckinView.vue` واستبدل `import { api, useAuthStore } from '@resort-os/core'` بـ `import client from '@/api/client'` و `import { useAuthStore } from '@/stores/auth'`.

**4. VITE_API_URL في production يجب أن يكون فارغاً:**
```
VITE_API_URL="" → client.ts baseURL = '' → relative /api/ → nginx proxy → backend:8005
```
لو اتبنى بـ `http://localhost:8000` = كارثة في production.

**5. public_site container:**
لا يزال موجوداً في `docker-compose.prod.yml` كـ fallback. لا يصله أي traffic من nginx. احذفه بعد 48h من التأكد من استقرار `marketing_site` في production، مع حذف مرجعه من `depends_on` في service `nginx`.

**6. الـ Docker build context للـ marketing_site:**
```yaml
build:
  context: /home/wego/projects/elkheima-marketing-website  # مسار مطلق
  dockerfile: Dockerfile
```
هذا مسار مطلق على الـ VPS — تأكد أن المجلد موجود على الـ VPS قبل الـ deploy.

---

#### سادساً — أوامر التحقق

```bash
# تأكد من الـ build الجديد
cd /home/wego/projects/elkheima-marketing-website
npm run build

# تأكد من الـ Docker
cd /home/wego/projects/resort-os
docker compose -f docker-compose.prod.yml build marketing_site
docker compose -f docker-compose.prod.yml config --quiet

# تأكد من الـ pnpm workspace
cd frontend
pnpm install

# اختبر الـ marketing_site container محلياً
docker run --rm -p 3099:80 resort-os-marketing_site:latest
curl -s -o /dev/null -w "%{http_code}" http://localhost:3099/s/test
# المتوقع: 200
```

---

#### سابعاً — للـ deploy على VPS

```bash
# 1. نقل المشروع الجديد للـ VPS (لو مش موجود)
rsync -av /home/wego/projects/elkheima-marketing-website/ user@vps:/home/wego/projects/elkheima-marketing-website/

# 2. build وتشغيل
cd /home/wego/projects/resort-os
docker compose -f docker-compose.prod.yml up -d --build marketing_site

# 3. بعد 48h من الاستقرار — احذف public_site
# في docker-compose.prod.yml: احذف service public_site
# و احذف public_site من depends_on في service nginx
docker compose -f docker-compose.prod.yml up -d --remove-orphans
```

---

## 9. Required handoff

Every implementation handoff must state:

- what changed and why;
- assumptions and accepted decisions used;
- important files changed;
- migrations and compatibility impact;
- commands run with exact pass/fail/not-run results;
- security, authorization, finance, RTL, and accessibility impact where
  relevant;
- remaining risks and intentionally deferred work;
- whether a commit was created (default: no).

Independent reviews must use the severity and evidence format in
`docs/agent-workflow/REVIEW_TEMPLATE.md`.
