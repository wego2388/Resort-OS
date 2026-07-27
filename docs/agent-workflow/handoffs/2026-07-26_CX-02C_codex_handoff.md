# CX-02C — Backend branch membership/session foundation handoff

Date: 2026-07-26  
Owner: Codex  
Status: **IMPLEMENTED — READY FOR REVIEW / DEPLOYMENT INTEGRATION**  
Commit/push/deploy: **not performed**

## Outcome

CX-02C's backend foundation is implemented without using
`Employee.branch_id` as an authorization source:

- `user_branch_memberships` is the live authorization source.
- `RefreshToken.active_branch_id` scopes active branch per refresh family,
  so two devices for the same user can stay on different branches.
- login chooses a branch only when the choice is unambiguous.
- refresh rotation copies the active branch.
- every authenticated request revalidates the live session/PIN branch against
  active membership and active `Branch`.
- public bootstrap and branch-switch contracts are implemented.
- ordinary branch operations require the resource branch to equal the
  server-resolved active context.
- super-admin bypasses membership, but does **not** bypass explicit active
  branch selection.
- PIN switch carries a signed `bid`, revalidates membership, and rejects a
  cross-branch target with `PIN_BRANCH_MISMATCH`.
- no backend `branch_id ?? 1`, `branch_id or 1`, or first-id fallback exists.
- a safe fresh-production CLI creates the first named branch without demo
  business data.

## Migration

CX-02C migration:

```text
b7e2c4a91f60_user_branch_memberships.py
down_revision = dc6bfb5b79e8
```

The revision is frozen. While this slice was being completed, CL-02B added:

```text
b7e2c4a91f60 -> c4d8e2f6a901 (current head)
```

The CX-02C migration:

1. creates `user_branch_memberships`;
2. adds uniqueness/check constraints and the partial unique active-default
   index;
3. adds nullable `refresh_tokens.active_branch_id` with `ON DELETE SET NULL`;
4. adds the composite session-context index;
5. backfills one active/default membership from each linked Employee;
6. backfills ordinary live refresh families only from one valid active
   default;
7. never guesses membership for unlinked users and never chooses the first
   branch.

PostgreSQL validation was run on an isolated clone of the development DB:

```text
upgrade dc6bfb5b79e8 -> b7e2c4a91f60    PASS
linked Employee rows                         10
backfilled memberships                       10
pinned live refresh rows                    144
downgrade -> dc6bfb5b79e8                 PASS
membership table absent after downgrade     PASS
active_branch_id absent after downgrade     PASS
upgrade -> b7e2c4a91f60                   PASS
```

The isolated database `cx02c_migration_test_20260726` was removed after
validation. The development database itself was not upgraded/downgraded.

## API contract

### `GET /api/v1/auth/bootstrap`

Returns:

- `contract_version=1`
- current user
- allowed active branches
- `allowed_branch_ids`
- account `default_branch_id`
- session `active_branch_id`
- `requires_branch_selection`
- effective permissions evaluated for the active branch

The response is `Cache-Control: no-store`.

### `PUT /api/v1/auth/active-branch`

Body:

```json
{"branch_id": 20}
```

Rules:

- requires a live access token bound to a refresh family (`sid`);
- locks User first, then the live refresh row, matching refresh rotation lock
  order;
- ordinary users need an active membership in an active branch;
- super-admin can choose any active branch;
- updates only that refresh family;
- records `active_branch_switched` AuditLog with branch IDs and the public
  session reference only;
- never logs a refresh token, family secret, or token hash.

Error codes:

```text
403 BRANCH_ACCESS_DENIED
409 BRANCH_CONTEXT_REQUIRED
409 SESSION_CHANGED
```

### PIN switch

- the terminal's active branch is mandatory;
- the target identity must have a live membership in the same branch;
- issued JWT contains `bid`;
- `bid` is revalidated from DB on every request;
- cross-branch switch returns:

```text
403 PIN_BRANCH_MISMATCH
```

## Fresh production bootstrap

Production seed remains prohibited. The first branch is created with:

```bash
cd backend
.venv/bin/python -m app.admin_bootstrap init-first-branch \
  --email owner@example.com \
  --code WSR-001 \
  --name "El Kheima Beach" \
  --name-ar "الخيمة بيتش" \
  --timezone Africa/Cairo
```

Properties:

- accepts only a named, active, non-demo super-admin;
- validates the branch payload and IANA timezone;
- serializes on the named User row, making an empty-table race safe;
- creates only the branch — no rooms, menus, rates, or synthetic business
  records;
- binds an active/default membership;
- binds the account's live refresh rows that still have null branch context;
- records `first_branch_bootstrapped`;
- exact rerun is a no-op;
- conflicting branch state fails closed and must use the authenticated control
  plane.

## Main implementation files

```text
backend/alembic/versions/b7e2c4a91f60_user_branch_memberships.py
backend/app/admin_bootstrap.py
backend/app/core/deps.py
backend/app/core/kernel/auth/router.py
backend/app/core/kernel/auth/service.py
backend/app/core/kernel/models/user.py
backend/app/core/me_router.py
backend/app/modules/core/api/router.py
backend/app/modules/core/models.py
backend/app/modules/core/schemas.py
backend/app/modules/core/services.py
backend/tests/test_admin_bootstrap_cleanup.py
backend/tests/test_api/test_auth_branch_bootstrap.py
```

Existing branch-bound test helpers were migrated from Employee-only setup to
explicit memberships in:

```text
backend/tests/conftest.py
backend/tests/test_api/test_beach.py
backend/tests/test_api/test_beach_http.py
backend/tests/test_api/test_core_http.py
backend/tests/test_api/test_dining_http.py
backend/tests/test_api/test_dining_paid_atomicity.py
backend/tests/test_api/test_finance_http.py
backend/tests/test_api/test_food_cost_report.py
backend/tests/test_api/test_guest_alerts.py
backend/tests/test_api/test_permissions.py
backend/tests/test_api/test_pms_coverage.py
backend/tests/test_api/test_pms_http.py
backend/tests/test_api/test_pms_branch_isolation_http.py
backend/tests/test_api/test_pos_full_cycle_http.py
backend/tests/test_api/test_refund_after_payment_http.py
backend/tests/test_api/test_service_location_tokens.py
backend/tests/test_api/test_step_up_control_plane.py
backend/tests/test_api/test_super_admin_invariants.py
```

These are test-contract updates only. No production Employee fallback or
Employee/membership dual-write was added.

## Verification

Passed:

```text
Python compile on all CX-02C implementation/migration files
git diff --check
alembic heads/history
PostgreSQL isolated upgrade -> downgrade -> upgrade
CX-02C auth/bootstrap/switch tests
refresh-family/session tests
PIN tests including cross-branch red-team case
branch-isolation suites across beach/dining/finance/PMS/alerts/WebSocket
first-branch bootstrap idempotency/audit test
```

The final full backend run reached 100%. It had exactly two failures, both
outside CX-02C and introduced by the concurrent CL-02B public-contact privacy
contract:

```text
tests/test_api/test_hub_blog.py::TestContactForm::test_contact_creates_lead
  old fixture omits new required contact_forms.public_reference

tests/test_api/test_hub_http.py::TestContactForm::test_submits_form_and_creates_crm_lead
  old payload no longer satisfies the new CL-02B consent/privacy schema
```

All other tests in that full run passed or were intentionally skipped.
The two CX-02C tests added after that run (refresh branch copy and PIN
cross-branch rejection) passed in the final targeted run.

## Deliberately not included

Per the parent task boundary and the final instruction to stop expansion:

- no frontend active-branch integration was started;
- no admin membership CRUD/step-up UI was added in this foundation slice;
- no real production branch/room/menu/rate data was invented;
- no VPS/deploy/DNS/TLS action was performed;
- no commit or push was performed.

## Next safe execution order

1. Review this handoff and CX-02C diff.
2. Let CL-02B repair its two stale public-contact tests and validate current
   Alembic head `c4d8e2f6a901`.
3. Run the full backend suite again.
4. Upgrade a staging DB to the current head and inspect preflight/backfill
   counts before production.
5. Run the named account bootstrap/onboarding, then `init-first-branch` only
   on a truly empty production branch table.
6. Implement frontend bootstrap/branch chooser/API injection as a separate
   slice.
