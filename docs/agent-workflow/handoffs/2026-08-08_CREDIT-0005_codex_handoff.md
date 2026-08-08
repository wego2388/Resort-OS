# CREDIT-0005 — Personal Credit Account pre-deploy handoff

**Date:** 2026-08-08 (Africa/Cairo)
**Owner:** Mohamed
**Implementer / final reviewer:** Codex
**Status:** READY_FOR_DEPLOY_APPROVAL / PRODUCTION_UNCHANGED

## Outcome

Decision 0005 is implemented locally for customer and employee personal credit
accounts. Dining and Beach can settle against the account, accountants can collect
cash/bank payments, managers can correct movements, Staff has a management screen,
and Owner has read-only receivables visibility.

The original draft's GL `1200` was rejected because it is the live inventory
account. Personal receivables use the new branch-scoped GL `1160`; folio
receivables remain `1150`.

No SSH, upload, migration, container restart, commit, push, or VPS write was made
for this package. Production remains on Alembic `f8aa1f0fabba` and the currently
active release.

## Financial and operational invariants

- Every `charge`, `payment`, `refund`, and `reversal` owns a posted balanced
  JournalEntry; no best-effort financial paths.
- `CreditAccount.current_balance` is a locked projection of the immutable
  `balance_delta` ledger and cannot become negative.
- Customer/employee ownership is XOR and branch scoped at DB and service layers.
- Only PostgreSQL `55P03` is translated to a retryable lock conflict.
- A sale source and an idempotency intent cannot be charged twice.
- Multiple partial sale refunds are allowed, but their sum cannot exceed the
  original charge. A partial unique DB index still permits only one exact reversal.
- Dining split refunds use a cumulative allocation target so repeated cent-level
  refunds finish at the exact original credit tender.
- Beach void reverses the credit movement and original journal; it never posts a
  fake cash reversal.
- Dining/Beach source rows, inventory/capacity, account ledger, projection, audit,
  and journals commit or roll back as one transaction.
- Credit API roles are exact-role checked as well as permission checked; owner and
  `hr_manager` do not inherit financial writes from role level alone.
- Credit and chat responses, including error responses, carry `Cache-Control:
  no-store`.

## Main implementation areas

- Migration: `backend/alembic/versions/c9d4e5f6a7b8_add_personal_credit_accounts.py`
- Credit module: `backend/app/modules/credit/`
- Dining integration: schemas, policy, router, and services under
  `backend/app/modules/dining/`
- Beach integration: model, schemas, router, and services under
  `backend/app/modules/beach/`
- Authorization/registries: core permission catalog, policy, schema validation,
  Alembic registry, seed registry, app middleware, and test registry.
- Staff UI: `/admin/credit-accounts`, Dining payment modal, Beach POS, route/nav,
  core endpoints, and Arabic/English strings.
- Owner read-only metrics: owner schemas/services/router and Now screen/API types.
- Decision record: `docs/decisions/0005-personal-credit-account.md`.

## Verification evidence

- Credit acceptance: **21/21 passed**.
- Credit + Beach + Dining + Dining HTTP focused gate: **242/242 passed**.
- Full backend: **2565 collected، 100%، exit 0، zero failures**.
- Repository collection: **2565 tests collected** after the final acceptance case.
- El Kheima frontend: **95/95 passed**; Arabic/English parity **6259 keys each**.
- `pnpm type-check:all`: passed for El Kheima and Owner.
- Production frontend build with `VITE_PUBLIC_SITE_URL=https://elkheima.com`:
  passed for El Kheima and Owner. Only the existing large-chunk advisory remained.
- PostgreSQL 16 fresh full-chain upgrade, downgrade to `f8aa1f0fabba`, and
  re-upgrade: passed. The `payment_method` source column and filtered unique
  reversal index were verified in PostgreSQL.
- Alembic: one head, `c9d4e5f6a7b8`.
- `scripts/agent-check.sh`: passed.
- `git diff --check`: passed.

## Final full-backend result

The final run used the unchanged implementation tree after all financial fixes and
acceptance cases were complete: **2565 tests collected، progress reached 100%،
process exit 0، zero failures**. Expected skips and test-only weak-secret warnings
did not fail the gate.

## Pre-deploy gate after Mohamed approves

1. Re-read `git status` and stage only reviewed project files; explicitly exclude
   local artifacts such as `test.db` and unrelated handoffs.
2. Create the release commit and record its SHA; do not deploy a dirty anonymous
   tree.
3. Validate production environment without printing secrets, then create and
   structurally verify a timestamped PostgreSQL dump.
4. Record current image IDs/digests and create rollback tags/manifest.
5. Build the affected backend, worker/beat, Staff, and Owner images from the exact
   release source; run import/config preflight.
6. Apply Alembic `c9d4e5f6a7b8`, verify tables/constraints/index/GL `1160`, then
   replace services in dependency order.
7. Run internal and external health checks, authenticated credit smoke checks,
   restart-count/log checks, and a short monitored canary.

## Rollback rule

- Preserve the pre-deploy DB dump and current image digests before migration.
- If rollback happens before any real credit rows are written, the migration can be
  downgraded to `f8aa1f0fabba` and the prior images restored.
- Once real credit data exists, do **not** casually downgrade because the downgrade
  drops the new ledger tables. Prefer a forward fix; if full rollback is required,
  restore the verified pre-deploy DB dump and prior images as one coordinated unit.
- GL `1160` intentionally remains on downgrade because posted accounting history
  must never lose its chart account.

## Known non-blocking output

- Test configuration prints warnings for deliberately weak test-only secrets.
- JSDOM reports `window.scrollTo` as unimplemented during passing router tests.
- Vite reports an existing chunk-size advisory for the main Staff bundle.
