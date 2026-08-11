# Security & Finance Remediation — 2026-08-11

Status: **in progress**, written incrementally as each section completes.
This is the required closing report per the task brief's acceptance
criteria (item 10): files modified, migrations, tests + results,
deployment steps, dry-run commands, rollback plan, production
reconciliation needed.

Branch: `claude/CX-02C-frontend-auth-bootstrap`.

---

## Section 1 — Source unification (finance/crud.py, finance/schemas.py)

**Finding: no merge was needed.** Compared this branch's full
`backend/app/` tree against the actual deployed content on
`/opt/resort-os` (not just the two named files — the VPS's own git
checkout is stale/never-committed, so its `git status` reports ~320
"modified" files that are really just bookkeeping noise; the real content
was fetched via `rsync` and diffed directly).

Result: only 7 files differ at all between this branch and what's
actually running in production, and in every case **this branch is a
strict superset** — production has nothing unique that this branch is
missing:

- `finance/crud.py`, `finance/schemas.py` — commit `92aa769`'s
  `account_code`/`account_name` on `JournalLineRead` + `selectinload`
  eager loading already present here, absent on the VPS's deployed copy.
- `inventory/crud.py`, `maintenance/crud.py` — same commit's N+1 fixes,
  same story.
- `admin_bootstrap.py` — this branch already has the `--role` flag for
  bootstrapping an `owner` account; production doesn't.
- `analytics/api/router.py`, `analytics/schemas.py` — differ only because
  of this session's own `avg_check_per_cover` addition (unrelated to this
  remediation, made earlier in the same session).

No code change was required for this section. Verification method: full
`rsync` of `backend/app/` from the VPS into a scratch directory, then
`diff -rq` against the local tree (excluding `__pycache__`).

---

## Section 2 — Owner permission enforcement (TOP PRIORITY)

### The vulnerability, confirmed live before any fix

`enforce_owner_write_policy()` (Decision 0004 §Isolation model item 4)
existed in `app/modules/owner/owner_policy.py` but had **zero call sites**
anywhere in the application — not wired into the owner router, not wired
anywhere else. Confirmed live: a valid `POST /api/v1/crm/customers`
request (`{"branch_id": 1, "full_name": "Exploit Test Customer"}`) from an
`owner`-role session returned **201 Created**, a real customer row.

The existing "fail-closed" tests (`tests/test_owner_phase2.py`,
`tests/test_owner_phase10.py` — the latter is literally named after
Decision 0004's own Phase 8 "security review" gate) did not catch this
because every one of them sent an **invalid** payload (missing the real
required field, e.g. `"name"` instead of `"full_name"`) and accepted
`403 OR 422 OR 404` as a pass. The request failed Pydantic validation
before ever reaching any policy check, regardless of whether one existed.
This is the exact anti-pattern the task brief warned against.

### The fix

New `enforce_owner_access_policy()` (renamed from
`enforce_owner_write_policy`, same file), wired as a **FastAPI
application-level dependency** (`FastAPI(dependencies=[...])` in
`app/main.py`) — not a router-level one, because the real exposure was in
*other* modules' routers (crm/beach/hub/inventory) that have no
owner-aware gate of their own. Router-level wiring on the owner module
alone would have been a no-op against the actual vulnerability.

Behavior:
- Not an `owner` session (or unauthenticated / any other role) → no-op,
  defers entirely to the endpoint's own auth chain.
- `super_admin` → always passes (Decision 0003 invariant #1, unchanged).
- `owner` on `GET/HEAD/OPTIONS` → allowed only under `/api/v1/owner/*`,
  `/api/v1/auth/*` (self-service), or `/health`. Every other prefix is
  403, including read-only browsing — new hardening beyond Decision
  0004's original write-only scope, per this review's explicit ask.
- `owner` on `POST/PUT/PATCH/DELETE` → allowed only if `route.name` is in
  `OWNER_WRITE_ALLOWLIST` (unchanged registry: self-service auth actions,
  `OwnerWatchlist` writes, allocation-rule **draft** actions — never
  `activate`).

Real regression hit and fixed during implementation: an app-level
dependency also attaches to WebSocket routes, which have no HTTP
`Request` object — the naive `request: Request` signature crashed every
WebSocket test in the suite (`TypeError: missing 1 required positional
argument`), and a naive `Request | None` fix broke OpenAPI schema
generation for every route in the app (`Invalid args for response
field`). Resolved with FastAPI's documented dual-parameter pattern
(`request: Request = None, websocket: WebSocket = None`, each its own
exact type) — verified against the full suite.

### Allocation Rules — branch-trust and race-condition fixes

`app/modules/owner/api/router.py` / `services.py` / `crud.py`:

- `GET /allocation-rules` accepted `branch_id: int = 1` as a **client
  query parameter**, unchecked — real IDOR, any branch's cost-allocation
  rules readable by guessing the number. Parameter removed entirely;
  branch is now derived the same way every other endpoint in this router
  already does (`_get_branch(user)`, from the authenticated session).
- `POST /allocation-rules/draft` trusted `data.branch_id` from the
  request body. Now overwritten server-side before use (same pattern
  already used for `OwnerWatchlist`).
- `PATCH`/`DELETE /allocation-rules/{rule_id}` looked up the rule by
  `rule_id` alone, no branch check — an owner could edit/delete a draft
  belonging to a branch they have no membership in by guessing an id.
  Both now take the session's branch and reject (generic "not found",
  not "wrong branch" — avoids confirming cross-branch id existence) when
  it doesn't match.
- `crud.create_allocation_rule_draft`'s `MAX(version) + 1` had no
  locking — a genuine race between two concurrent draft-creation requests
  for the same branch. Fixed with `SELECT ... FOR UPDATE` on the
  branch's existing rows (project's established pattern, CLAUDE.md §13
  ⓫) plus a new DB-level `UNIQUE(branch_id, version)` constraint as a
  second line of defense for the empty-branch case where no row exists
  yet to lock.
- `services.update_draft` validated only the fields present in a given
  PATCH request, not the merged total against the row's existing values
  — a partial update could silently push the real total over 100%
  (proven: the pre-existing passing test `test_owner_allocation_rule_draft_crud`
  demonstrated exactly this scenario, 45+30+20+10=105%, with no
  rejection). Now computes the full merged total before accepting.

### Watchlist

- `OwnerWatchlist`'s unique constraint was `(owner_user_id, metric_key)`
  — missing `branch_id`, which would incorrectly block pinning the same
  metric in two different branches. Migration changes it to
  `(owner_user_id, branch_id, metric_key)`.
- `remove_watchlist_item` looked up the item by `(id, owner_user_id)`
  only, no branch check — same IDOR family as allocation rules. Fixed.

### Database session model (Decision 0004 §Isolation model item 5)

New `app/modules/owner/db_sessions.py`: `get_owner_read_db` (SELECT-only,
every business table — used by all report/aggregation GETs) and
`get_owner_metadata_write_db` (INSERT/UPDATE/DELETE on
`owner_watchlist`/`owner_allocation_rules` only — used by the 5 owner-table
write endpoints). Both fall back to the normal shared engine when no
dedicated restricted-role DSN is configured (`OWNER_READ_DATABASE_URL` /
`OWNER_METADATA_WRITE_DATABASE_URL`, new optional settings), so the app
still runs in dev without the extra Postgres roles provisioned — the real
DB-level restriction only activates once
`scripts/provision_owner_db_roles.sql` has been run against an
environment and those two env vars point at the resulting roles.

All 27 `db: DbDep` parameters in the owner router were replaced with one
of the two restricted sessions (20 read, 7 metadata-write) — the router
no longer has a single endpoint using the full-privilege session.

**Live-verified against real PostgreSQL** (not SQLite — this project has
been burned before by SQLite silently ignoring privilege/locking
behavior, CLAUDE.md §13 ⓫), `tests/test_owner_db_session_privileges.py`:
provisions the two roles against a disposable throwaway database and
proves, with real INSERT/UPDATE statements over a real connection bound
to each restricted role: the read role's writes fail with Postgres
`permission denied` on both `owner_watchlist` and (for the one deliberate
exception) succeed on `audit_logs` only; the metadata-write role can
write its own two tables but fails `permission denied` against an
operational table (`branches`). 6/6 passed live.

`tests/test_owner_allocation_rule_concurrency.py` — live Postgres,
two real concurrent HTTP-equivalent draft-creation calls on separate
threads/connections for the same branch: both succeed, versions are `2`
and `3` (never colliding), final row count is exactly 3. 1/1 passed live.

### Audit logging

`_log_owner_audit()` helper in the router, using the project's existing
`core.crud.create_audit_log` (no second audit mechanism invented). Wired
into the 6 drill-down endpoints (`sales/item-detail`, `beach/type-detail`,
`expense-detail`, `procurement-detail`, `product-detail`, `search`) and
the 5 owner-table write actions (watchlist add/remove, allocation-rule
draft create/update/delete). Deliberately **not** wired into `/now` or
`/performance` (routine polling) — the two pre-existing tests proving
that stay green, and a new test
(`test_audit_log_written_on_allocation_rule_draft_action`) proves a real
action *does* produce exactly one new row with the correct actor/branch.

Provisioning script grants both restricted roles `INSERT`-only on
`audit_logs` specifically (Decision 0004's own anticipated exception) —
proven live as the one write both roles *can* do, everything else still
rejected.

### Error message hygiene

All 19 occurrences of `raise HTTPException(500, {"message": str(exc)})`
in the owner router replaced with a shared `_owner_error()` helper: logs
the real exception server-side (`logger.exception`), returns a fixed
generic message + stable error code to the client. (The five remaining
`str(e)` sites in the router are deliberate, safe `ValueError` messages
the service layer already crafts for the user — e.g. "rule not found",
"total exceeds 100%" — not raw exception leakage, left unchanged.)

### Files changed

```
backend/app/main.py                                    (global dependency wiring)
backend/app/core/config.py                              (2 new optional settings)
backend/app/modules/owner/owner_policy.py                (rewritten policy)
backend/app/modules/owner/api/router.py                  (branch fixes, sessions, audit, error hygiene)
backend/app/modules/owner/services.py                    (branch checks, PATCH total validation)
backend/app/modules/owner/crud.py                        (FOR UPDATE lock, branch-filtered lookups)
backend/app/modules/owner/models.py                       (constraint updates)
backend/app/modules/owner/db_sessions.py                  (NEW — restricted sessions)
backend/alembic/versions/90f2a4c81b3e_*.py                 (NEW — unique constraints)
scripts/provision_owner_db_roles.sql                       (NEW — Postgres role provisioning)
backend/tests/conftest.py                                  (dependency_overrides for new sessions)
backend/tests/test_owner_phase2.py                         (fixed false-pass tests + new coverage)
backend/tests/test_owner_phase10.py                        (fixed false-pass tests + new coverage)
backend/tests/test_owner_db_session_privileges.py           (NEW — live Postgres)
backend/tests/test_owner_allocation_rule_concurrency.py     (NEW — live Postgres)
```

### Migration

`90f2a4c81b3e_owner_allocation_rule_watchlist_.py` — `Revises: b7c8d9e0f1a2`
(the prior single head). Adds `uq_owner_allocation_rule_branch_version`
and replaces `uq_owner_watchlist_user_metric` with
`uq_owner_watchlist_user_branch_metric`. Reversible (`downgrade()`
restores the original constraint). No data migration needed — both
tables are new-ish and low-volume; no existing rows are expected to
violate the new constraints, but this hasn't been verified against the
production database's actual current rows (see "Production
reconciliation needed" below).

### Deployment / dry-run notes for this section

1. `alembic upgrade head` (adds the two constraints — will fail loudly if
   any existing production row already violates
   `(branch_id, version)` or `(owner_user_id, branch_id, metric_key)`;
   check first with a read-only query before deploying, see below).
2. Deploy the application code (global policy + router changes) — no
   env var is required for the write-block and read-prefix hardening to
   take effect immediately; that part activates the moment the code
   ships.
3. **Separately, optionally, later**: run
   `scripts/provision_owner_db_roles.sql` against production and set
   `OWNER_READ_DATABASE_URL` / `OWNER_METADATA_WRITE_DATABASE_URL` to
   activate the DB-level session restriction. The app runs correctly
   without this step (falls back to the shared engine) — this is
   defense-in-depth on top of the already-fixed application-level policy,
   not a blocker for shipping the core fix.

**Pre-deploy check recommended** (read-only, safe to run any time):
```sql
-- Confirm no existing row would violate the new constraints before
-- alembic upgrade head runs against production.
SELECT branch_id, version, COUNT(*) FROM owner_allocation_rules
  GROUP BY branch_id, version HAVING COUNT(*) > 1;
SELECT owner_user_id, branch_id, metric_key, COUNT(*) FROM owner_watchlist
  GROUP BY owner_user_id, branch_id, metric_key HAVING COUNT(*) > 1;
```

### Production reconciliation needed

None identified yet for this section — the queries above have not been
run against the actual production database as part of this session (no
production DB access from this environment); run them before the
migration deploys.

---

## Section 3 — Hub confirmation + PMS booking atomicity

### The bug, confirmed by reading the code

`hub.services.confirm_booking()` called `pms.services.create_booking()` /
`create_bundle_booking()`, each of which did its **own internal
`db.commit()`** (releasing the room's `SELECT FOR UPDATE` lock at that
point), and then `confirm_booking()` did a **second, separate**
`db.commit()` to mark the `HubOnlineBooking` as confirmed and link
`pms_booking_id`. If the process failed between the two commits (crash,
exception, timeout), a real PMS room reservation would exist with no
traceable link back to the Hub request that created it. Separately,
`confirm_booking()` read `booking.status` without any row lock, so two
concurrent confirmation requests for the same Hub booking could both
observe `status == "pending"` and both attempt to create a PMS booking.

### The fix

- `pms.services.create_booking()` / `create_bundle_booking()` gained an
  optional `commit: bool = True` parameter (default preserves existing
  behavior for all 6 other call sites — the `POST /pms/bookings` /
  `.../bundle` endpoints, `seed.py`, `hist_pms_bookings.py`,
  `crm.services`' lead-to-booking conversion — verified by reading every
  call site before making the change, per the task's explicit warning
  not to add `commit=False` without checking every caller). Hub's two
  confirmation paths (`_confirm_room_type_leg`/`_confirm_bundle_leg`)
  pass `commit=False`.
- New `hub.crud.lock_online_booking_for_update()` — `SELECT ... FOR
  UPDATE NOWAIT` on the `HubOnlineBooking` row, mirroring the project's
  established pattern (`beach.crud.lock_inventory_for_update`,
  `pms.crud.lock_room_for_booking`). `confirm_booking()` now locks the
  row first, before any status check.
- `confirm_booking()` is now genuinely **idempotent**: if the row is
  already `status == "confirmed"` (a prior call already succeeded — e.g.
  a client retry after a network timeout that actually delivered), it
  returns the existing booking instead of raising. Any other non-pending
  status (`cancelled`) still raises, unchanged.
- New `HubConfirmationConcurrencyError`, raised only when the lock
  genuinely can't be acquired — distinguished from any other
  `OperationalError` via `app.core.db_errors.is_lock_not_available()`
  (checks the real Postgres SQLSTATE `55P03`, not just "some DB error
  happened"), the same helper already used correctly in
  `crm.services`' loyalty-redeem lock. Mapped to HTTP 409 in the router.
- On any failure inside the PMS-creation attempt (strict mode — the
  request carries a guest-facing price quote), `confirm_booking()` now
  explicitly `db.rollback()`s before re-raising, so the failed attempt
  never leaves a partial write for the *next* successful confirm to
  build on top of.

**Noted but explicitly out of scope for this pass**: `beach.services`'
own three `_lock_*_or_raise` helpers (`_lock_inventory_or_raise`,
`_lock_contract_day_or_raise`, `_lock_location_or_raise`) catch any
`OperationalError` and convert it to a domain concurrency error
*without* checking `is_lock_not_available` first — the same
over-broad-catch anti-pattern `db_errors.py`'s own docstring says was
fixed elsewhere (Gate 1B) but apparently wasn't propagated to these
three call sites. Real finding, not part of this section's scope (Hub/
PMS specifically) — flagged here for a future pass.

### Tests

- `tests/test_api/test_hub.py::test_forced_failure_after_pms_insert_leaves_no_orphan_booking`
  — monkeypatches the post-PMS-creation step to raise, proves the whole
  operation rolls back: `HubOnlineBooking` stays `pending`, zero PMS
  `Booking` rows exist afterward. Runs on the regular SQLite suite (this
  is atomicity/rollback, not lock contention — SQLite handles plain
  transaction rollback correctly, it only ignores row-level `FOR
  UPDATE`).
- `tests/test_api/test_hub.py::test_reconfirm_already_confirmed_is_idempotent`
  — replaces the old `test_cannot_confirm_already_confirmed` (behavior
  intentionally changed per this task's explicit requirement; the old
  test's expectation was the bug). `test_cannot_confirm_cancelled_booking`
  added alongside it to keep coverage of the genuinely-invalid-state
  rejection path.
- `tests/test_hub_confirm_concurrency.py` (**live Postgres**, new) — two
  real concurrent `confirm_booking()` calls on separate threads/
  connections for the same Hub booking (2 real rooms available): exactly
  one succeeds and links to exactly one PMS `Booking` row; the other
  gets `HubConfirmationConcurrencyError` immediately (`NOWAIT`, not a
  hang). 1/1 passed live.
- Full `tests/test_api/test_hub.py`, `test_hub_http.py`, `test_hist_hub.py`,
  `test_api/test_pms*.py`, `test_hist_pms_bookings.py` — all green after
  the change (45 + 10 respectively, no regressions).

**Scope decision, documented**: the bundle-booking path
(`_confirm_bundle_leg` → `create_bundle_booking(commit=False)`) shares
the *exact same* locking/rollback/idempotency mechanism at the
`confirm_booking()` level as the room-type path — the fix isn't
per-path, it's at the point where both paths converge. Given that, a
second full live-Postgres concurrency test for the bundle path
specifically would exercise identical machinery with different data
setup, not different logic. Not written, to keep this section's already
substantial test surface focused; the atomicity test
(`test_forced_failure_after_pms_insert_leaves_no_orphan_booking`) could
be trivially extended to a bundle scenario if a future review wants
that specific combination covered explicitly.

### Files changed

```
backend/app/modules/pms/services.py                (commit=False param, 2 functions)
backend/app/modules/hub/services.py                  (lock, idempotency, rollback, new exception)
backend/app/modules/hub/crud.py                       (NEW lock_online_booking_for_update)
backend/app/modules/hub/api/router.py                  (409 mapping for the new exception)
backend/tests/test_api/test_hub.py                      (fixed test, +2 new tests)
backend/tests/test_hub_confirm_concurrency.py            (NEW — live Postgres)
```

No migration required (no schema change — the fix is transaction/locking
behavior only).

### Deployment notes

Pure application-code change, takes effect the moment the code deploys.
No environment variable, no data backfill, no production reconciliation
needed for this section specifically.

---

## Section 4 — Financial operations must fail atomically with their journal entry

### The vulnerability

`post_simple_revenue_journal()` (`finance/services.py`) — the shared
journal-posting helper used by 6 modules — defaults to `strict=False`:
on any failure (missing account for the branch, zero/negative amount,
currency-conversion failure, unexpected exception) it logs an error and
returns `None` instead of raising. Every call site that relied on the
default therefore let the *operational* half of a financial action
succeed and commit while the *accounting* half silently vanished — no
exception, no 500, nothing in the response to the caller. A missing
account row for a branch (a data/config problem, not a user error) was
enough to make real money movement invisible to the ledger.

Confirmed call sites doing this before the fix: leasing accrual/receipt/
deposit/cash-log (fixed earlier this session, see leasing section of
`PROJECT_STATUS.md`), timeshare down-payment/installment/maintenance/
cancellation-refund, PMS checkout settlement, folio payment/void, and
HR salary-advance/advance-payment disbursement.

A second, more subtle version of the same bug: several of these
operational functions had no `try/except` wrapper at all, so even when
the journal call *did* raise, only the DB objects created via `flush()`
were implicitly rolled back at process/session teardown — not
deterministically at the point of failure. Two operations in particular
mutated state via a separate `crud.*` call before the journal step
(`crud.cancel_contract` setting `status="cancelled"`, `crud.void_payment`
setting `voided_at`) with no guarantee that mutation would be undone if
the journal step then failed.

### The fix

Applied uniformly across every listed call site:

1. `strict=True, commit_cost_centers=False` added to the
   `post_simple_revenue_journal()` call. `strict=True` makes a missing
   account / zero-amount / conversion failure raise
   `FinancialConfigurationError` instead of returning `None`.
   `commit_cost_centers=False` is required alongside it — the default
   `commit_cost_centers=True` path calls `db.commit()` internally via
   `ensure_default_cost_centers`, which breaks any enclosing
   `db.begin_nested()` SAVEPOINT and, more generally, defeats the
   atomicity we're adding. (Discovered via a real
   `InvalidRequestError: Can't operate on closed transaction` failure
   while fixing leasing earlier in the session — documented here again
   because it recurred identically in every module.)
2. The enclosing operational function wrapped in
   `try: ... db.commit(); return X except Exception: db.rollback(); raise`
   so a journal failure rolls back every DB change made earlier in the
   same call, not just the journal insert itself.
3. `FinancialConfigurationError` mapped to `HTTP 503
   {"code": "FINANCIAL_CONFIGURATION_ERROR", ...}` at the router layer
   (the existing, already-established pattern from `beach/api/router.py`
   and this session's leasing fix) — the caller gets a clear "system not
   configured" signal rather than a generic 500 or, worse, a false 200.

**Zero-amount edge case (real bug found while doing this, not
theoretical):** `strict=True` makes `amount <= 0` raise, same as a
missing account. Two call sites can legitimately be invoked with a
zero amount as a *valid business no-op*, not a failure:
`timeshare._post_deferred_revenue_journal` (a contract can legitimately
have `down_payment=0`) and `pms._post_checkout_journal` (a fully
comped stay can legitimately have `total_amount=0` after subtracting
extra charges). Both are now guarded with an explicit
`if amount > 0:` check *before* the strict call, so a zero amount skips
posting entirely (no journal, no error) exactly as before, while a
*missing account for a non-zero amount* now correctly raises. Without
this guard, `test_zero_down_payment_does_not_post_journal` would have
started failing — a real behavior regression, not just a test needing
updating — so this was fixed in the application code, not glossed over
in the test.

### Per-module changes

**Timeshare** (`app/modules/timeshare/services.py`):
- `create_contract`: `_post_deferred_revenue_journal` call now guarded
  by `if contract.down_payment and contract.down_payment > 0:`; whole
  function already had try/except from earlier in the session.
- `_post_deferred_revenue_journal`, `_post_installment_payment_journal`,
  `_post_maintenance_payment_journal`,
  `_post_contract_cancellation_refund_journal`: all four
  `post_simple_revenue_journal` calls now `strict=True,
  commit_cost_centers=False`.
- `pay_installment`, `pay_maintenance_due`: already wrapped in
  try/except from earlier in the session.
- `cancel_contract`: now wrapped in try/except (`crud.cancel_contract`'s
  `status="cancelled"` mutation is rolled back if the refund journal
  then fails).
- `app/modules/timeshare/api/router.py`: `FinancialConfigurationError`
  → 503 mapping added to `create_contract`, `pay_installment`,
  `pay_maintenance_due`, `cancel_contract`.

**PMS** (`app/modules/pms/services.py`):
- `_post_checkout_journal`: the settlement post now guarded by
  `if total_amount > 0:` (comp-stay edge case above) and
  `strict=True, commit_cost_centers=False` when it does post.
- `checkout_booking`: wrapped in try/except — a journal failure now
  rolls back the booking-status change, room-status change, and
  housekeeping-task creation together, so a failed checkout doesn't
  leave a "checked_out" booking with a room stuck in
  `checkout_pending` and no accounting trail.
- `app/modules/pms/api/router.py`: `FinancialConfigurationError` → 503
  on `POST /pms/bookings/{id}/checkout`.

**Folio (Finance)** (`app/modules/finance/services.py`):
- `add_payment`: wrapped in try/except; `strict=True,
  commit_cost_centers=False` on the settlement journal.
- `void_payment`: wrapped in try/except (the `crud.void_payment`
  mutation and the `RevenueAuditLog` write are rolled back together
  with the reversal journal if that journal fails);
  `strict=True, commit_cost_centers=False` on the reversal journal.
- `app/modules/finance/api/router.py`: `FinancialConfigurationError` →
  503 on `POST /finance/folios/{id}/payments` and
  `POST /finance/payments/{id}/void`.

**HR** (`app/modules/hr/services.py`):
- `create_salary_advance`, `create_advance_payment`: both wrapped in
  try/except; `_post_advance_disbursement_journal` now
  `strict=True, commit_cost_centers=False`.
- `app/modules/hr/api/router.py`: `FinancialConfigurationError` → 503
  on `POST /hr/salary-advances` and `POST /hr/advance-payments`.
- **Explicitly not touched in this section**: `cancel_salary_advance`
  still posts no reversing journal entry at all on cancellation — that
  is Section 6's bug (creation posts Dr 1180/Cr 1100, cancellation
  posts nothing), left for that section rather than folded in here.
- **Explicitly not touched**: `_post_payroll journal` (called from
  `approve_payroll_run`) already has its own `if not accs: return`
  tolerant pattern and is not in the task brief's explicit list for
  this section; left as-is.

### Tests

Every listed operation now has a "missing account → whole operation
fails, zero partial state" test, per the task brief's explicit
requirement:

- `tests/test_api/test_timeshare.py::test_missing_accounts_fails_contract_creation_atomically`
  (rewrite of a test that used to assert the *old* silent-swallow
  behavior — its own docstring said so explicitly; now asserts
  `FinancialConfigurationError` and zero contracts persisted).
- `tests/test_api/test_pms.py::test_checkout_fails_atomically_when_account_missing`
  (new — asserts booking stays `checked_in` and room stays `occupied`).
- `tests/test_api/test_finance.py::test_missing_accounts_fails_payment_atomically`
  (rewrite of the equivalent old-behavior test in
  `TestPaymentSettlementJournalPosting`; asserts zero payments
  persisted).
- `tests/test_api/test_hr.py::test_create_salary_advance_fails_atomically_when_account_missing`
  (new — asserts zero `SalaryAdvance` rows persisted).
- Leasing's equivalent (`test_pay_payment_fails_atomically_when_account_missing`)
  was added earlier in the session when leasing was fixed.

**Fixture fallout (expected, not a regression):** enabling `strict=True`
converted dozens of pre-existing tests across
`test_timeshare*.py`, `test_pms*.py`, `test_finance*.py`, and
`test_hr*.py` from "silently posts nothing" to "raises
`FinancialConfigurationError`", because those tests' branch/contract
fixtures never seeded a chart of accounts — they were unknowingly
relying on the exact bug this section fixes. Every affected fixture
(`make_finance_accounts`, `make_branch_committed`,
`make_contract_with_maintenance`, the `contract`/`branch` pytest
fixtures, etc., one per test file) was updated to seed the accounts
each module's journal calls actually reference (1100/1110/1120 cash-
equivalent accounts, 4600/4650 timeshare revenue, 4100/1150/2160/2165
PMS/folio accounts, 1180 HR advance-receivable), following the
established `seed_leasing_accounts` pattern from earlier in the
session. This is the same category of fix CLAUDE.md §3.7 requires
("لو السلوك اتغيّر، الاختبارات لازم تتغيّر معاه") — not a weakening of
any assertion.

### Verification

```
tests/test_api/test_timeshare_http.py tests/test_api/test_timeshare.py
tests/test_api/test_timeshare_maintenance.py tests/test_timeshare_leasing_concurrency.py
tests/test_api/test_timeshare_calendar_visits.py tests/test_api/test_timeshare_unit_pairs.py
tests/test_api/test_timeshare_maintenance_fee_rules.py tests/test_api/test_timeshare_peak_seasons.py
tests/test_api/test_timeshare_owner_portal_http.py tests/test_api/test_timeshare_report_audit.py
tests/test_hist_timeshare.py tests/test_engines/test_timeshare_engine.py
tests/test_tasks/test_timeshare_tasks_extended.py tests/test_tasks/test_timeshare_tasks.py
  → 292 passed, 2 skipped

tests/test_api/test_pms.py tests/test_api/test_pms_http.py tests/test_hist_pms_bookings.py
tests/test_api/test_pms_branch_isolation_http.py tests/test_api/test_pms_permissions_http.py
tests/test_api/test_pms_coverage.py tests/test_tasks/test_pms_tasks.py
tests/test_api/test_hub.py tests/test_api/test_hub_room_booking.py
  → all passed (68 in the two core files alone)

tests/test_api/test_finance.py tests/test_api/test_finance_http.py
tests/test_api/test_finance_depreciation_and_reconciliation_http.py
tests/test_api/test_finance_checks.py tests/test_tasks/test_finance_tasks_coverage.py
  → 123 + 101 + 32 = 256 passed

tests/test_hist_hr.py tests/test_api/test_hr_http.py tests/test_api/test_hr_me_http.py
tests/test_api/test_hr.py tests/test_api/test_hr_attendance_import.py
tests/test_engines/test_hr_engine.py tests/test_tasks/test_hr_tasks_extended.py
tests/test_tasks/test_hr_tasks_coverage.py
  → 306 passed, 2 pre-existing failures unrelated to this change
    (TestPayroll::test_calculate_payroll_no_si_config_raises /
    test_calculate_payroll_no_tax_brackets_raises — cross-file test-order
    pollution; reproduced identically on the unmodified codebase via
    `git stash`, confirmed NOT caused by this section's changes, left
    unfixed as out of scope)
```

Combined targeted run
(`test_pms.py test_hr.py test_finance.py test_leasing_http.py
test_timeshare_leasing_concurrency.py`): **293 passed, 2 skipped**.

### Files changed

```
backend/app/modules/timeshare/services.py            (strict=True ×4, cancel_contract try/except, zero-amount guard)
backend/app/modules/timeshare/api/router.py           (FinancialConfigurationError → 503 ×4 endpoints)
backend/app/modules/pms/services.py                   (checkout atomicity + zero-amount guard)
backend/app/modules/pms/api/router.py                 (FinancialConfigurationError → 503)
backend/app/modules/finance/services.py                (add_payment/void_payment atomicity)
backend/app/modules/finance/api/router.py               (FinancialConfigurationError → 503 ×2 endpoints)
backend/app/modules/hr/services.py                      (salary advance/advance payment atomicity)
backend/app/modules/hr/api/router.py                    (FinancialConfigurationError → 503 ×2 endpoints)
backend/tests/test_api/test_timeshare.py                (rewritten test, account fixtures, 1 new atomicity test)
backend/tests/test_api/test_timeshare_http.py            (account fixture seeding)
backend/tests/test_api/test_timeshare_maintenance.py      (account fixture seeding)
backend/tests/test_api/test_timeshare_unit_pairs.py        (account fixture seeding)
backend/tests/test_api/test_timeshare_peak_seasons.py       (account fixture seeding)
backend/tests/test_api/test_timeshare_report_audit.py        (account fixture seeding)
backend/tests/test_tasks/test_timeshare_tasks.py               (account fixture seeding)
backend/tests/test_api/test_pms.py                       (account fixtures, 1 new atomicity test)
backend/tests/test_api/test_pms_http.py                    (account fixture seeding)
backend/tests/test_api/test_finance.py                       (rewritten test, account fixtures)
backend/tests/test_api/test_finance_http.py                    (account fixture seeding, idempotent helper)
backend/tests/test_api/test_hr.py                                (account fixtures, 1 new atomicity test)
backend/tests/test_api/test_hr_http.py                              (account fixture seeding)
```

No migration required (no schema change).

### Deployment notes

Pure application-code change — takes effect the moment the code
deploys. **Production risk to flag explicitly**: any branch on
production missing one of the accounts a given operation now requires
(1100/1110/1120/1150/1180/2160/2165/4100/4600/4650, depending on
module) will see that operation start returning `503
FINANCIAL_CONFIGURATION_ERROR` instead of silently succeeding with no
journal entry, the moment this deploys. This is the intended fix (the
old behavior was the bug), but it means the chart-of-accounts
completeness check from the 2026-07-27 incident write-up above (§ "حساب
إيراد الغرف الموحّد") should be re-verified against current production
before this section ships, so a legitimately configured branch doesn't
start rejecting real transactions. No data backfill or reconciliation
needed for this section itself.

---

*(Sections 5–10 to be appended as they complete.)*
