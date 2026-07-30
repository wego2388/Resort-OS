# El Kheima Beach Resort OS — Current Agent Instructions

These instructions apply to the entire repository. They contain stable working
rules only; current status and production evidence live in the documents
listed below. The superseded instruction file is archived under
`docs/archive/2026-07-execution/AGENTS_LEGACY_THROUGH_2026-07-29.md` and must
not be executed.

## 1. Authority and read order

Read in this order before changing code or production:

1. The user's latest explicit request and accepted decisions.
2. This file.
3. `CLAUDE.md` for the engineering charter.
4. `docs/README.md` for the current documentation map.
5. `wagdy.md` for the owner's current plain-language decisions.
6. `PROJECT_STATUS.md` for dated technical facts.
7. `docs/audits/EL_KHEIMA_FINAL_EXECUTION_PLAN_AR.md`.
8. `docs/agent-workflow/EL_KHEIMA_EXECUTION_BOARD.md`.
9. The latest handoff named by the board.
10. Task-specific code, migrations, tests, and decision records.

Current authority, highest first:

1. The user's latest explicit instruction.
2. Accepted decision records and an approved task brief.
3. This file and the stable engineering rules in `CLAUDE.md`.
4. Current code, schema, tests, and runtime evidence.
5. The live plan, board, status, and owner dashboard.

Everything under `docs/archive/` is historical evidence only. Never execute
commit, deploy, DNS, data, or VPS instructions from it.

## 2. Current ownership and product facts

- Mohamed owns commercial scope, real master data, and final operational
  Go/No-Go.
- Codex is the implementation lead and final technical reviewer under the
  owner's current authorization.
- The exact brand spelling is **El Kheima Beach**.
- This is one resort, not an invented SaaS multi-tenant product.
- There is one operational branch today. Do not expose a branch switcher, but
  preserve fail-closed branch isolation and permission checks.
- `dining` is the active food-and-beverage bounded context; do not recreate
  retired `restaurant` or `cafe` modules.
- The staff app is `frontend/apps/el-kheima`.
- The marketing/guest site is the independent repository
  `/home/wego/projects/elkheima-marketing-website`; do not recreate the
  retired monorepo public app.
- QR guest-service, bilingual staff UX, and super-admin invariants are defined
  in `docs/decisions/0001-*`, `0002-*`, and `0003-*`.
- Production is domain-based: `elkheima.com` and `www.elkheima.com` serve the
  marketing site, while `app.elkheima.com` serves the staff app. Do not run or
  edit the user-owned `scripts/wait-dns-then-switch.sh`; the cutover was
  completed through the reviewed provider/API workflow.

## 3. Working mode

- Review or audit: inspect and report; do not mutate systems unless the user
  also asked for implementation.
- Diagnose: establish the cause and evidence; do not silently expand into a
  fix.
- Implement: make the requested bounded change, verify it, update current
  documentation, and hand off the result.
- Production operation: use a rollback point, controlled scope, health checks,
  and recorded evidence.

Do not turn a broad product idea into an unbounded rewrite. Search for the
existing implementation and preserve user-owned changes.

## 4. Start checklist

1. Run `git status --short --branch`, `git branch --show-current`,
   `git rev-parse --short HEAD`, and `git worktree list`.
2. Inspect overlapping local changes before editing. Never discard or absorb
   unrelated user work.
3. Do not `git pull` blindly; fetch and inspect divergence first.
4. Do not develop directly on `main` unless the user explicitly requires it.
5. Read the nearest models, schemas, CRUD, services, routers, frontend callers,
   migrations, and tests for the workflow in scope.
6. Run `bash scripts/agent-check.sh` as the read-only repository baseline.
7. State any business assumption that cannot be proved from current evidence.

## 5. Engineering guardrails

### Architecture

- Preserve router -> service -> CRUD -> model boundaries.
- Keep pure calculation code in `backend/app/resort_os/` independent of
  FastAPI and SQLAlchemy.
- Prefer the existing modular monolith and shared frontend packages.
- Do not add a service, abstraction, or dependency without a concrete need.

### Data, finance, and concurrency

- Use `Decimal`/`Numeric` for money.
- Preserve historical prices and totals.
- Posted financial records are immutable in normal workflows; correct them
  through explicit reversal/replacement.
- Financial writes need a transaction boundary, authorization, source
  reference, and audit trail.
- Use constraints, idempotency, and row locking where races can break an
  invariant.
- Use `backend/app/resort_os/timezone_utils.py` and the existing UTC storage
  convention.
- Never invent master data or run demo seed logic in production.

### Security

- Backend authorization is mandatory; frontend visibility is not authority.
- Derive trusted branch, outlet, location, price, and ownership server-side.
- Preserve last-super-admin, TOTP, step-up, and audit invariants.
- Use the existing encrypted-field pattern for supported PII.
- Never print or commit secrets, tokens, passwords, cards, or production env
  values.

### Frontend

- Staff-facing copy must work in Arabic and English through shared i18n.
- Preserve RTL/LTR behavior, keyboard access, focus behavior, and contrast.
- Personal preferences, operational settings, global settings, and secrets
  are different scopes.
- Offline data and queued operations must be scoped to the authenticated user,
  branch, and module.

### Schema and API compatibility

- Never delete migration history or edit an applied migration when a forward
  migration is safer.
- Check `alembic heads`; keep one head unless a deliberate merge is required.
- Destructive schema changes require an impact and recovery plan.
- Preserve public contracts by default and document affected callers when a
  contract must change.

## 6. Git and file safety

- Never use `git reset --hard`, `git clean -fd`, history rewriting, or blanket
  checkout.
- Do not stage with `git add .`; stage reviewed paths explicitly.
- Commit, push, and deploy only when the current user request authorizes them.
  Record the exact branch and commit; never silently update `main`.
- One implementation task should have one owning worktree.
- Preserve unrelated untracked files. In particular,
  `scripts/wait-dns-then-switch.sh` is user-owned and outside current scope.

## 7. Production safety

- Use SSH key access as the non-root operations user described in the latest
  VPS handoff. Do not weaken SSH, UFW, Fail2ban, or loopback-only bindings.
- Do not build from or clean an unknown dirty production worktree.
- Prefer immutable release directories tied to a reviewed commit and archive
  digest.
- Before schema/application changes, create a fresh DB backup and preserve the
  prior image IDs/tags.
- Derive required Compose secrets in memory; never duplicate or print them.
- Use the active `docker-compose.prod.domain.yml` override and resolve the
  exact current release through `/opt/resort-os-current`.
- Replace the smallest service set, wait for health, then verify externally.
- Do not restore a database merely to roll back compatible application code.
- Do not reset or broadly replace DNS, change Chatbot governance/provider
  flags, or import real data without the relevant owner decision. The current
  DNS records and rollback snapshot are documented in `PROJECT_STATUS.md`.

The current host, release, image IDs, backup paths, and rollback evidence are
in `PROJECT_STATUS.md` and the latest handoff. Do not copy stale values from
historical guides.

The host health baseline is `resort-os-healthcheck.timer`. Changes to its
thresholds or checks require a manual pass and a documented failure-path test.

## 8. Validation contract

Run targeted checks while developing and the full affected gates before a
release:

```bash
# Repository
bash scripts/agent-check.sh
git diff --check
git status --short --branch

# Backend
cd backend
.venv/bin/pytest tests/ -v
.venv/bin/alembic heads

# Frontend
cd ../frontend
pnpm run type-check:all
pnpm --filter el-kheima test:frontend
pnpm run build:all

# Production Compose, with the required environment supplied safely
cd ..
docker compose config --quiet
docker compose -f docker-compose.prod.yml config --quiet
```

Use commands that actually exist in the current repository. Do not claim a
gate passed from stored counts alone.

## 9. Documentation and handoff

When status or a decision changes:

1. Update `wagdy.md`.
2. Update `PROJECT_STATUS.md` with evidence.
3. Update the final plan if a gate changed.
4. Update the execution board with the current task only.
5. Create a handoff for a closed release or production change.
6. Archive superseded instructions instead of leaving conflicting live files.

Every handoff states: what changed, why, source commit, important files,
migration compatibility, exact checks, production effect, rollback point,
remaining risks, and commit/push/deploy status.
