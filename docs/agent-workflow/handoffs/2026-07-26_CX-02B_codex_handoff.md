# Handoff CX-02B — Codex

- **Implementer:** Codex
- **Base SHA:** `27cc217`
- **Target:** uncommitted diff in `/home/wego/projects/resort-os`
- **Branch/worktree:** `main` in the shared worktree
- **Status:** ready for independent review; no commit/push/deploy performed

## Outcome

CX-02B closes the immediate PMS branch/object-isolation gap left by CX-02A.
An authenticated role or explicit capability is no longer enough by itself:
every internal PMS route now also proves that the acting employee belongs to
the target branch. Only the active super-admin control plane retains global
access.

The packet also rejects cross-branch foreign-key relationships before write:

- room → room type;
- rate plan → room type;
- booking → room, customer, or rate plan;
- housekeeping task → room or assigned employee.

Foreign read/mutation attempts return 403, invalid cross-branch relationships
return 400, missing objects return 404, and the WebSocket closes with 4403.

## Files changed

### Permission and branch resolution

- `backend/app/modules/core/services.py`
- `backend/app/modules/core/schemas.py`
- `backend/app/core/kernel/auth/router.py`

### PMS enforcement

- `backend/app/modules/pms/api/router.py`
- `backend/app/modules/pms/services.py`

### Regression coverage

- `backend/tests/test_api/test_pms_branch_isolation_http.py` (new)
- `backend/tests/test_api/test_pms_permissions_http.py`
- `backend/tests/test_api/test_pms_http.py`
- `backend/tests/test_api/test_pms_coverage.py`

No chat, marketing, config, rate-limit, `main.py`, or Alembic migration file
was changed by this packet.

## Security contract

### Acting branch

The current authoritative source is:

```text
User.id → HR.Employee.user_id → HR.Employee.branch_id
```

- staff without a linked Employee row fail closed;
- staff linked to Branch A cannot query or mutate Branch B;
- object-ID routes load the object, then verify its `branch_id`;
- query/body routes verify the requested `branch_id` before service work;
- PMS room WebSocket subscriptions perform the same check;
- super-admin is the only global branch bypass.

### Permission precedence

`require_permission` now resolves a branch-scoped `UserPermission` against the
employee's real branch instead of the nonexistent `User.branch_id`. A
branch-specific explicit deny therefore overrides the role fallback, and a
narrow branch grant works without granting access to another branch.

The permission action validator now accepts every action in the central
catalog (`check_in`, `check_out`, `early_late`, `manage`, `update_status`,
`run`, etc.). The regular permission payload and step-up intent share one
pattern to prevent future drift.

## Independent negative-path coverage

The new A/B suite proves:

1. foreign room types, rooms, availability, bookings, housekeeping, rate
   plans, and night-audit queries are denied;
2. foreign booking reads by ID are denied while super-admin reads succeed;
3. check-in, checkout, cancel, early/late, room status, housekeeping, rate
   plan, and night-audit mutations are denied and leave rows unchanged;
4. unlinked staff are denied;
5. a narrow branch grant does not expand to another branch;
6. foreign WebSocket subscription closes with 4403 while the home stream
   answers heartbeat;
7. cross-branch room type/customer/rate-plan/employee relationships fail
   before any PMS row is created or changed.

Old coverage fixtures were updated to create real branch-linked employees
instead of relying on implicit global access or hard-coded employee IDs.

## Validation evidence

```text
.venv/bin/pytest -q \
  tests/test_api/test_pms_coverage.py \
  tests/test_api/test_pms_branch_isolation_http.py \
  tests/test_api/test_pms_http.py \
  tests/test_api/test_pms_permissions_http.py
PASS — 58 tests

.venv/bin/pytest -q \
  tests/test_api/test_pms_branch_isolation_http.py \
  tests/test_api/test_pms_http.py \
  tests/test_api/test_pms_permissions_http.py \
  tests/test_api/test_permissions.py \
  tests/test_api/test_super_admin_invariants.py \
  tests/test_api/test_step_up_control_plane.py
PASS — 96 tests

.venv/bin/pytest -q --ignore=tests/test_api/test_chat.py
PASS — 2,132 collected; no failures (the expected platform skips remain)

backend/.venv/bin/python -m compileall for changed Backend modules
PASS

git diff --check
PASS
```

The full run intentionally excluded only `tests/test_api/test_chat.py` because
Claude was actively rewriting CL-01R in the same worktree during validation.
An earlier moving-worktree run showed 14 transient chat failures plus the old
PMS fixture failures; after fixing the PMS fixtures, the complete non-chat
suite above is green.

Warnings observed are pre-existing test-environment warnings:

- pytest-asyncio default fixture-loop scope deprecation;
- deliberately weak test `SECRET_KEY`.

## Deliberate limitation / CX-02C

This is safe single-branch containment using the schema that exists today.
`Employee.user_id` is unique, so one login currently belongs to one branch.
The final multi-branch bootstrap contract still needs a dedicated
`user_branch_memberships` model/migration with:

- active/default branch;
- membership status and role/permission context;
- server-issued active-branch selection;
- frontend bootstrap that removes `branch_id ?? 1`;
- branch-aware offline queue ownership.

That migration is deliberately deferred to CX-02C until Claude's chat
migration is stable, avoiding concurrent Alembic-head edits in the shared
worktree. The current implementation is fail-closed and suitable as
containment, but multi-branch staff workflows are not yet complete.

## Reviewer focus

Claude should review:

1. every internal PMS route for capability + branch checks;
2. fetch-object-then-authorize ordering on ID routes;
3. super-admin as the only cross-branch bypass;
4. cross-branch relationship validation and HTTP status mapping;
5. branch-scoped grant/deny behavior in the shared permission resolver;
6. WebSocket 4403 behavior;
7. the explicit boundary between CX-02B containment and CX-02C membership.
