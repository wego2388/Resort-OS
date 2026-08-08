# CREDIT-0005 — Personal Credit Account deployment handoff

**Date:** 2026-08-08 (Africa/Cairo)
**Owner:** Mohamed
**Implementer / final reviewer:** Codex
**Status:** DEPLOYED / PRODUCTION_VERIFIED

## Outcome

Decision 0005 is implemented and deployed for customer and employee personal
credit accounts. Dining and Beach can settle against the account, accountants can
collect cash/bank payments, managers can correct movements, Staff has a management
screen, and Owner has read-only receivables visibility.

The original draft's GL `1200` was rejected because it is the live inventory
account. Personal receivables use the new branch-scoped GL `1160`; folio
receivables remain `1150`.

Mohamed approved the deployment. Implementation commit `dd26a1f` was pushed and
deployed, followed by commit `1d77e7b` removing the duplicated Owner HTTP server
block discovered by the production `nginx -t` preflight. Production is active at
`/opt/resort-os-releases/1d77e7b` with Alembic `c9d4e5f6a7b8 (head)`.

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

## Production deployment record

- Implementation commit: `dd26a1f7fb67a08d83306043c5660695fa8ea41c`.
- Final release/config commit: `1d77e7b72a3fa3e5e52bbb9a92a8aa06608fbb45`.
- Active symlink: `/opt/resort-os-current -> /opt/resort-os-releases/1d77e7b`.
- Verified pre-deploy DB dump:
  `/var/backups/resort-os/database/resort_os_20260808_180257.dump`, `609846`
  bytes, SHA-256
  `1bd9d33edebb667eb4d42b53fd2f4040aaeaa9c90a9c69efec61ab6bc616d70d`.
- Rollback image manifest:
  `/var/backups/resort-os/source-releases/dd26a1f-rollback-images.txt`.
- Final exact-source archive:
  `/var/backups/resort-os/source-releases/1d77e7b.tar.gz`, SHA-256
  `1ef3bea7541a2354b712faa6b4d0ec044978093746e501e66b7ff78365506827`.
- Production environment validation and Compose config validation passed without
  printing secrets. New backend import and Alembic preflight passed.
- Migration `f8aa1f0fabba -> c9d4e5f6a7b8` applied successfully. Both new tables
  are present; initial credit-account/transaction row counts are `0 / 0`; branch
  count and GL `1160` count are both `1`.
- Images built from the exact release source: backend, Celery worker/beat, Staff,
  and Owner. Replacement order was backend → worker/beat → Staff/Owner → Nginx.
- Backend, worker, beat, Staff, and Owner are healthy with `RestartCount=0`;
  Nginx is running with `RestartCount=0` and a clean `nginx -t`.
- `/health` and `/health/ready` report production DB and Redis `ok`.
  `elkheima.com`, `www`, `app`, and `owner` return HTTP `200`; Owner HTTP redirects
  with `301`. Anonymous Credit and Owner protected probes return `401`, confirming
  the routes are live and guarded. No production financial test row was created.
- `resort-os-healthcheck.service` returned success. Strict post-deploy scans found
  zero `ERROR`/`CRITICAL`/`Traceback` entries in the changed-service logs.

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
