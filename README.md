# El Kheima Beach — Resort OS

An internal ERP + PMS + POS system for a beach resort in Sharm El Sheikh, Egypt
(code name `resort-os`). It covers front office (rooms/bookings/housekeeping),
finance (double-entry accounting, cashier shifts, ETA e-invoicing), HR
(Egyptian payroll law), inventory, restaurant/cafe POS with a live kitchen
display, beach operations (capacity/surge/B2B contracts), timeshare contracts,
CRM, maintenance, and a small guest-facing website + QR ordering flow — all
behind one role-based staff application.

This is an internal ops tool, not a public product. If you're reading this on
the VPS, see [`DEPLOYMENT.md`](./DEPLOYMENT.md) for how to stand it up.

## Tech stack

**Backend**
- FastAPI (Python 3.11+), SQLAlchemy 2.0, Alembic migrations
- PostgreSQL 16, Redis 7 (cache, rate limiting, Celery broker/result backend)
- Celery (worker + beat) for background jobs and scheduled tasks (e.g. night audit)
- Auth, security, DB session management, caching, error handling, health
  checks, logging, Sentry, Celery, WhatsApp/email notifications, and PDF/Excel
  report generation are all owned directly by this repo in
  `backend/app/core/kernel/` — no external shared-package dependency, no
  second build context, nothing else to clone.

**Frontend** — pnpm monorepo (Vue 3 + Vite + Pinia + TailwindCSS), two apps:

| App | Path | Audience | Dev port |
|---|---|---|---|
| `el-kheima` | `frontend/apps/el-kheima` | Staff (POS, KDS, back office, waiter, employee self-service portal) — one app, role-gated routing | 3001 |
| `public` | `frontend/apps/public` | Guest-facing booking/marketing site + QR ordering (scan a table/sunbed QR to order from the restaurant or cafe menu), beach check-in, and post-stay survey — all unauthenticated | 3007 |

(The old standalone `qr` app was merged into `public` on 2026-07-06 — both were unauthenticated guest-facing apps with no reason to be separate deployments.)

Shared code lives in `frontend/packages/`: `@resort-os/core` (API client, Pinia
stores, composables) and `@resort-os/ui` (shared Vue components, e.g. `LoginView`).

## Quickstart (local dev)

Requirements: Python 3.11+, Node 20+, pnpm 10, Docker (for Postgres + Redis).

```bash
# 1. Backend env + install
cp backend/.env.example backend/.env      # fill in secrets — see DEPLOYMENT.md §3 for how to generate them
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 2. Frontend deps
cd ../frontend && pnpm install

# 3. Start everything (Postgres + Redis via Docker, backend, Celery worker+beat,
#    and all 3 frontend apps)
cd .. && bash scripts/start.sh
# bash scripts/start.sh --no-frontend        backend only
# bash scripts/start.sh --apps="el-kheima"   pick specific frontend apps
```

Default login: `admin@resortos.local` / `Admin@123456` (`super_admin` — 2FA required).

Stop everything with `bash scripts/stop.sh` (add `--docker` to also stop Postgres/Redis).
Check what's running with `bash scripts/status.sh`.

### Tests

```bash
cd backend && source .venv/bin/activate
pytest tests/ -q                                          # full suite
pytest tests/ --cov=app --cov-report=term-missing -q      # with coverage
```

## Architecture overview

Backend domain code lives under `backend/app/modules/`, one directory per
business module, each following the same internal layering:

```
modules/<name>/
├── models.py     # SQLAlchemy ORM (Mapped[...], Decimal for money, never float)
├── schemas.py    # Pydantic request/response models
├── crud.py       # DB operations only — never raises HTTPException
├── services.py   # Business logic — raises ValueError / domain exceptions
└── api/router.py # HTTP layer — translates service errors into HTTP responses
```

The 14 modules: `core`, `finance`, `inventory`, `hr`, `restaurant`, `cafe`,
`pms`, `timeshare`, `beach`, `maintenance`, `crm`, `analytics`, `hub`,
`leasing` — all permanently active (no enable/disable toggle; this is a
single-property deployment, not a multi-tenant product with per-customer
feature sets).

Pure business logic with no FastAPI/SQLAlchemy dependency (Egyptian payroll
calculation, beach capacity/surge rules, timeshare installment schedules,
discount rules, folio validation) lives separately in `backend/app/resort_os/`
so it can be unit-tested without a database.

Shared infrastructure (JWT auth, password hashing, DB session, Redis cache,
Celery app factory, PDF/Excel report building, error handlers, health checks,
logging, Sentry, WhatsApp/email notifications) lives in
`backend/app/core/kernel/` — see `CLAUDE.md` §6 for the full module map.

Database backups: `scripts/backup_db.sh` / `scripts/restore_db.sh` (see
`DEPLOYMENT.md` §10 for scheduling and disaster-recovery instructions).

For the deeper engineering charter (auth chain, role levels, critical
gotchas, security rules) see [`CLAUDE.md`](./CLAUDE.md).
