# Handoff CX-02A — Codex

- **Implementer:** Codex
- **Base SHA:** `27cc217`
- **Target:** uncommitted diff in `/home/wego/projects/resort-os`
- **Branch/worktree:** `main` in the shared worktree
- **Status:** ready for independent review; no commit/push performed

## Outcome

Internal PMS endpoints no longer treat “active account” as sufficient
authorization. Reads containing guest/stay/room operations and housekeeping
writes now use explicit permission-matrix gates with documented role
fallbacks.

The existing operational behavior remains:

- cashier/receptionist level 40 keeps daily PMS access;
- manager/admin role fallbacks keep their previous capabilities;
- active waiter/employee accounts are denied by default;
- a narrow explicit grant can allow a housekeeping employee without exposing
  bookings or unrelated PMS actions;
- an explicit deny overrides a manager role;
- active super-admin invariants remain intact.

## Files changed

- `backend/app/modules/core/permission_catalog.py`
- `backend/app/modules/pms/api/router.py`
- `backend/tests/test_api/test_pms_permissions_http.py`

No migration, model, config, `main.py`, rate-limit, or chat file was changed.

## Permission contract

| Resource | Action | Role fallback | Protected operations |
|---|---|---:|---|
| `pms.rooms` | `view` | 40 | room types, room list, availability |
| `pms.room_configuration` | `manage` | 80 | create room type/room |
| `pms.rooms` | `update_status` | 60 | change room status |
| `pms.bookings` | `view` | 40 | list/get bookings |
| `pms.bookings` | `create` | 40 | create booking |
| `pms.bookings` | `check_in` | 40 | check-in |
| `pms.bookings` | `check_out` | 40 | checkout |
| `pms.bookings` | `early_late` | 40 | early/late request |
| `pms.cancel_booking` | `execute` | 60 | cancel booking |
| `pms.housekeeping` | `view` | 40 | list tasks |
| `pms.housekeeping` | `update` | 40 | update/assign task |
| `pms.rate_plans` | `view` | 40 | list/get plans |
| `pms.rate_plans` | `manage` | 80 | create/update plans |
| `pms.night_audit` | `view` | 60 | audit history |
| `pms.night_audit` | `run` | 80 | run audit |

The unauthenticated `GET /pms/public/room-types` endpoint is intentionally
unchanged; it returns the public room-type projection and remains covered by
its existing tests/rate limit.

## Validation evidence

```text
.venv/bin/pytest -q tests/test_api/test_pms_permissions_http.py
PASS — 6 tests

.venv/bin/pytest -q \
  tests/test_api/test_pms_http.py \
  tests/test_api/test_pms_coverage.py \
  tests/test_api/test_permissions.py
PASS — 51 tests

.venv/bin/pytest -q \
  tests/test_api/test_pms.py \
  tests/test_api/test_pms_http.py \
  tests/test_api/test_pms_coverage.py \
  tests/test_api/test_pms_permissions_http.py \
  tests/test_api/test_permissions.py
PASS — 95 tests

.venv/bin/pytest -q tests/test_api/test_super_admin_invariants.py
PASS — 15 tests

backend/.venv/bin/python -m compileall for changed Backend modules
PASS

git diff --check
PASS
```

Warnings observed are pre-existing test-environment warnings:

- pytest-asyncio default fixture-loop scope deprecation.
- deliberately weak test `SECRET_KEY`.

## Security and compatibility notes

1. `require_permission` includes active-user validation and permits explicit
   grants/denies below/above the role fallback by design.
2. Replacing direct role dependencies is intentional: otherwise a level-20
   housekeeping employee with an explicit grant would still be blocked by a
   second cashier-level dependency.
3. Existing cashier/manager/admin HTTP lifecycle tests pass unchanged.
4. The public route is not accidentally covered by the internal permission.

## Known limitation / next CX-02 packet

This packet closes **capability authorization**, not branch/object isolation.
The current permission resolver cannot reliably apply a branch-scoped grant
because `User` has no real `branch_id`, and ID routes still need fetch-object
then branch-membership checks. CX-02B must add the membership/bootstrap
contract and enforce:

- query/body branch access;
- booking/room/task/rate-plan object branch access;
- WebSocket branch access;
- branch-scoped permission resolution.

Until CX-02B is accepted, PMS must not be considered production-ready.

## Reviewer focus

Claude should inspect:

1. Whether each internal PMS route maps to the intended permission/action.
2. Whether role fallback levels preserve receptionist workflows.
3. Explicit housekeeping grant and manager deny semantics.
4. Any route unintentionally left on `get_current_active_user`.
5. The separation between public room types and internal inventory.
6. The explicitly deferred branch/object isolation risk.

