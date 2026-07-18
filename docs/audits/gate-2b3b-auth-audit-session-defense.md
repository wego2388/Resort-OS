# Gate 2B3B — Authentication Audit & Session Defense

**Status: accepted after independent Codex review and acceptance hardening.**
Implemented and reviewed on branch
`gate-2b3b-auth-audit-session-defense`, based on the accepted Gate 2B3A work.
**Not pushed.** The implementation was reviewed as one complete three-slice
package before its local acceptance checkpoint.

**Date:** 2026-07-19

This gate is one coherent package delivered as three interlocking slices:

1. **Slice A** — a unified, bounded, secret-free authentication audit trail in
   the existing `AuditLog` table.
2. **Slice B** — refresh-token *families* with atomic single-use rotation and
   replay detection that revokes the whole family.
3. **Slice C** — a self-service session-management API + bilingual (AR/EN) UI,
   protected by the existing Gate 2B3A step-up mechanism.

No scope was added beyond the execution brief
(`docs/audits/gate-2b3b-execution-brief.md`): no typed settings registry, no
finance-domain step-up, no user→branch data model, no QR work, no Super Admin
"manage another user's sessions" screen, no new dependency.

## Baseline found before changing anything

- `AuthService` (`app/core/kernel/auth/service.py`) already had `_add_auth_audit`
  writing secret-free rows into the unified `AuditLog` (`entity_type =
  "user_authentication"`) for a handful of events (`password_changed`,
  `two_factor_enabled/disabled`, `step_up_*`, …), but **not** login
  success/failure/lockout, logout, session revoke, or refresh replay, and it
  recorded neither the client IP, User-Agent, nor request id.
- `RefreshToken` rotation (`rotate_refresh_token`) already did atomic
  single-use rotation via a conditional `DELETE` — but it *hard-deleted* the
  old row, so a reused token was simply "unknown" afterwards and its lineage
  could be neither detected nor revoked.
- Step-up (Gate 2B3A) provided a single-use, session-bound, scope-bound proof
  via `POST /auth/step-up` + `X-Step-Up-Token`, with a canonical scope-hash
  builder (`app/core/kernel/auth/step_up.py`), a `_STEP_UP_PURPOSES` frozenset,
  and per-purpose typed Pydantic intent models. This gate **extends** that, it
  does not build a parallel mechanism.
- The login endpoint's anti-enumeration protections (identical
  message/timing/status for unknown-email vs wrong-password via a dummy bcrypt
  compare) were in place and are preserved.
- The frontend axios client (`packages/core/src/api/client.ts`) already
  single-flights refresh (`_isRefreshing` + `_queue`), which materially
  affects the replay trade-off below.

## Slice A — Unified, bounded, secret-free authentication audit

All auth events are written into the **existing** `AuditLog` table (no parallel
table), following the exact Gate 2B3A pattern.

**Request context.** `AuthService.attach_request_context(ip, user_agent)` is
called once by the auth router's `get_auth_service` dependency. The IP is the
**trusted** client IP resolved with the app's existing proxy policy
(`app.core.rate_limit._client_ip` — honours `RATE_LIMIT_TRUSTED_PROXY_HOPS`,
never trusts a raw `X-Forwarded-For`). The User-Agent is sanitized
(`_sanitize_user_agent`: strips non-printable characters, caps at 255) before
storage. `request_id` is read ambiently from the correlation context var
(`app.core.kernel.correlation.get_request_id`), so it needs no threading
through method signatures. Non-HTTP callers (CLI, Celery, tests) simply record
no IP/UA.

**`_add_auth_audit(user, action, *, details=None, bounded=False)`** writes:
actor id (accepts a `User` or a bare id), stable action code, the trusted IP
and sanitized UA into the dedicated `AuditLog.ip_address`/`user_agent` columns,
and `request_id` inside the existing `new_data` JSON. It never writes an email,
password, TOTP/recovery code, or any token/hash.

**Events now covered:** `login_succeeded`, `login_failed` (known account, incl.
a `2fa` factor variant), `login_locked_out`, `login_blocked_locked` (attempt
against an already-locked account), `login_blocked_inactive`,
`password_reset_requested`, `password_reset_completed`, `password_changed`,
`two_factor_*`, `two_factor_recovery_code_used/regenerated`, `logout`,
`session_revoked`, `all_sessions_revoked`, and `refresh_token_replayed` — plus
the pre-existing `step_up_*`.

**Unknown-account decision (documented).** A login attempt for an email that
does not exist writes **no** `AuditLog` row — that is exactly the PII / write
amplification this gate must avoid (one DB row per anonymous bot request).
Instead a single structured `logger.warning` line records a **keyed,
non-reversible** HMAC fingerprint of the email (`_email_fingerprint`,
`HMAC-SHA256(SECRET_KEY, "auth-audit-email:" + casefold(email))[:16]`) plus the
IP — correlatable for operators, never a raw address, never an enumeration
oracle. This is the brief's "keyed HMAC / structured-log-only" option.

**Bounded persistence.** Failure events that a bot could repeat
(`login_failed`, `login_blocked_locked`, `login_blocked_inactive`) are written
with `bounded=True`, which gates the row behind
`rate_limit("auth-audit:{action}:{user_id}", 20, 300)`. The accept/reject of
the login itself is completely independent and unchanged — only the *logging*
of repeated failures is capped, so `AuditLog` cannot be amplified without
bound. `login_locked_out` (at most one per lockout window) and `login_succeeded`
are logged unbounded.

**Fail-closed vs best-effort (explicit).** Audit rows are `db.add`-ed into the
same transaction as the login state change and committed by the existing
commit; an audit-write failure raises and rolls the whole thing back, so it can
only ever turn a login into a *failure*, never a failure into a success. The
one deliberately best-effort path is the unknown-account structured log (a log
line, no DB write, cannot affect the result).

**Anti-enumeration preserved.** The unknown-email and wrong-password paths still
return the identical status/message and run the same dummy bcrypt compare; the
audit is server-side only (admin-visible) and is never surfaced to the client,
so it is not a side channel. The public `password-reset/request` response is
unchanged; `password_reset_requested` is audited only when a real account
exists, server-side.

## Slice B — Refresh-token families with atomic reuse detection

`RefreshToken` (`app/core/kernel/models/user.py`) gains, via forward migration
`b8f4d2a19c07`:

| column | purpose |
|---|---|
| `family_id` (varchar 64, indexed) | internal, random lineage key (`secrets.token_hex(16)`, never derived from `user_id`); revocation targets it |
| `family_public_id` (varchar 32, indexed) | separate non-secret handle the UI lists/revokes by — the internal `family_id`/`token_hash`/`successor_token_hash` are never exposed |
| `family_started_at` (timestamptz) | true session start, carried across every rotation (`created_at` resets each refresh, so it reads as "last activity") |
| `consumed_at` (timestamptz) | tombstone: set when this exact token is rotated — its presence makes a re-presentation a *provable* replay |
| `revoked_at` (timestamptz) | set on every live row of a family when the family is revoked |
| `successor_token_hash` (varchar 64) | debuggable lineage pointer (a one-way hash, never a usable secret) |
| `user_agent` (varchar 255) | limited, sanitized device description for the session list |

The bearer token itself remains **hash-only** (`token_hash`), exactly as before.

**Rotation (`rotate_refresh_token`)** — the concurrency boundary is a single
conditional `UPDATE`:

```
UPDATE refresh_tokens
   SET consumed_at = now(), successor_token_hash = :new
 WHERE id = :id AND consumed_at IS NULL AND revoked_at IS NULL AND expires_at > now()
```

Semantics, in order:

1. Token unknown → generic reject (no tombstone proves prior consumption).
2. `consumed_at IS NOT NULL` → **provable replay**: `_handle_replay` revokes the
   whole family (`_revoke_family`) **and** publishes a global access-token
   cutoff (`revoke_user_tokens`) — a detected theft warrants killing every
   access token immediately — then audits `refresh_token_replayed` (secret-free)
   and returns `None`.
3. `revoked_at IS NOT NULL` or expired → generic reject; never revive.
4. Otherwise: capture the family lineage into locals **before** any UPDATE, run
   the conditional UPDATE. Exactly one concurrent caller can flip `consumed_at`
   from NULL (Postgres row-lock serializes the two; the loser re-evaluates the
   `WHERE` against the committed state and affects 0 rows). The winner mints the
   successor in the same family; the loser returns `None` **without** revoking
   the family — it never observed a tombstone, so it is a benign double-submit,
   not a provable replay (brief slice B point 4).
5. Bounded cleanup: only *this user's own* expired rows are deleted on the
   success path (never a global sweep), keeping tombstones alive for replay
   detection until natural expiry, then reaping them off the hot path.

Password change / reset, 2FA enable/disable/regenerate, and bootstrap recovery
continue to fully clear the user's refresh rows (`delete_refresh_tokens_for_user`),
so those credential changes revoke every family. Logout (`revoke_session`) now
revokes the *current* token's whole family rather than deleting one row.

**Replay trade-off (documented honestly).** Two near-simultaneous refreshes of
the *same* token have two valid outcomes depending on interleaving: the benign
race (one successor survives) or, if the winner commits before the loser's
SELECT, the loser sees the tombstone and revokes the family (0 usable tokens).
The core invariant holds in both: **never a double-mint**. Treating the loser as
a replay is the deliberate security-first choice sanctioned by the brief. In
practice the frontend single-flights refresh, so a single tab never hits this;
only a genuine replay or a rare cross-tab simultaneous expiry does, and the
existing 401→logout interceptor re-logs in cleanly. Other devices' families are
untouched and self-heal on their next refresh.

## Slice C — Self-service session management API + bilingual UI

New endpoints on the kernel auth router (all `/api/v1/auth`, current-user only):

| endpoint | behaviour |
|---|---|
| `GET /sessions` | lists the caller's own active families as non-secret DTOs (`session_ref`, `started_at`, `last_active_at`, `expires_at`, `device`, `current`). The session owning the current refresh cookie is flagged `current`. Never exposes token/hash/internal family id. |
| `DELETE /sessions/{session_ref}` | revoke one owned family; **step-up required** (`session_revoke`, scope-bound to that ref). Missing header → 428; invalid proof → 403; ref not owned/gone → 404 (so a user cannot probe another user's sessions). |
| `POST /sessions/revoke-others` | revoke every family except the current one; **step-up required** (`other_sessions_revoke`, bound to the current session's public ref, which is re-derived server-side from the refresh cookie). No current cookie → 400. |
| `GET /security-activity?limit&offset` | paginated, allow-listed view of the caller's own auth events (only actions in `AUTH_AUDIT_ACTIONS`, only the caller's rows), whitelisted fields only (`id, action, at, ip_address, device, request_id`). |

HTTP login and refresh access tokens now carry a signed `sid` claim containing
the non-secret public session reference. The shared HTTP/WebSocket token
resolver verifies that `sid` still has a live refresh-family successor owned by
the same user. Therefore single-session and bulk revoke invalidate the target
access token **immediately**, without using the user-global cutoff and without
logging the caller's kept session out. Legacy/POS tokens without `sid` remain
backward compatible; the latter are short-lived and have no refresh session.

**Step-up reuse.** Two new purposes were added to the *existing* mechanism:
`_STEP_UP_PURPOSES`, typed intent models (`_SessionRevokeIntent{session_ref}`,
`_OtherSessionsRevokeIntent{keep_session_ref}` — both `extra="forbid"`, and
deliberately **reasonless**), scope builders (`session_revoke_scope`,
`other_sessions_revoke_scope`), and the issuance `if/elif` chain. Consumption
reuses `AuthService.consume_step_up` unchanged, via a small router-local
`_consume_session_step_up_or_raise` that mirrors the core router's helper (428
missing / generic 403 otherwise).

**Frontend** (`frontend/`, built by a parallel agent against this exact
contract): a new `views/account/SessionsView.vue` at route `/account/sessions`
(any authenticated user; reachable via an additive "Sessions & security" nav
link). It reuses `StepUpConfirmModal.vue` — extended, not duplicated — with a
new `requireReason?: boolean` prop (default `true`, so the two existing callers
are unchanged). When `false`, the modal renders no reason field, skips reason
validation, and posts **exactly** `{ ...intent }` (no `reason`), which is what
the `extra="forbid"` session intent models require. Fully AR/EN via `useI18n()`
(`account.sessions.*` / `account.securityActivity.*` namespaces in
`packages/core/src/i18n/locales/{ar,en}.json`, kept in parity), no forced
`dir="rtl"` anywhere (direction inherited, per Gate 2B3A's pitfall note),
loading/empty/error/success states, keyboard/screen-reader friendly, and no
step-up token or secret written to local/session storage.

## Migration and rollback

`b8f4d2a19c07` (`down_revision = ad7ed1e7329b`) is additive: it adds the seven
columns, backfills each pre-existing refresh row with its **own** isolated
family (`secrets.token_hex` per row, in Python so it is identical on Postgres
and SQLite — never one shared family, which would let one legacy token's replay
revoke unrelated rows) with `family_started_at = created_at`, and creates the
two indexes actually queried (`family_id`, `family_public_id`).

Verified on disposable, self-created-and-dropped Postgres databases:
`upgrade head` → `downgrade ad7ed1e7329b` → `upgrade head`, all clean, all seven
columns and both indexes present afterwards. Separately, three real legacy
refresh rows were seeded at `ad7ed1e7329b` and the upgrade produced **three
distinct families** with `family_started_at = created_at`.

**Rollback honesty:** once the app starts rotating the new families, a
downgrade drops the family/tombstone columns, so replay detection and the
session list stop working and in-flight lineage is lost. Existing refresh
*tokens* keep working as opaque bearer credentials (`token_hash`/`expires_at`
untouched); only the family hardening is removed. Nothing predating the
migration is destroyed by the upgrade. The cookie/CSRF/CORS contract is
unchanged; the refresh token is never moved into JavaScript.

## Bug found and fixed during implementation

`test_rotation_replaces_the_token_and_old_token_cannot_be_replayed` (Gate 2B1)
encoded the *old, weaker* semantics: after replaying a rotated parent token,
the fresh successor was expected to still work. That is precisely the hole this
gate closes — a proven replay must revoke the whole family. The test was updated
(renamed to `..._revoking_the_family`) to assert the stronger, correct behavior:
replaying the consumed parent both is rejected **and** kills the successor. This
is a deliberate, documented behavior change, not a weakened test.

## API compatibility

- `POST/GET/DELETE /api/v1/auth/sessions*` and `GET /api/v1/auth/security-activity`
  are new. No existing endpoint's contract changed.
- Login/refresh/logout/2FA/password-reset request/response shapes are byte-for-byte
  unchanged (only added audit side effects and, for logout/refresh, the
  family-aware revocation semantics described above).
- `StepUpConfirmModal`'s two existing callers are unaffected (`requireReason`
  defaults to `true`).

## Independent Codex review and acceptance hardening

The final review did not accept the self-verified diff on report trust. It
re-read the migration, auth/session transaction boundaries, API ownership,
frontend and tests, then found and fixed these confirmed gaps:

1. A targeted session revoke stopped refresh but left its already-issued access
   token usable for up to the configured 30-minute TTL. Real HTTP login/refresh
   tokens are now session-bound with `sid`, and the central resolver rejects a
   revoked family immediately.
2. `current_session()` accepted any valid refresh cookie without proving it
   belonged to the bearer user. It now takes `expected_user_id`; a mixed
   access-token/cookie pair cannot mark or preserve another user's family.
3. `revoke_other_sessions()` reported affected token rows, so a rotated family
   could be counted more than once. It now counts distinct live families.
4. Family revoke racing successor creation was serialized only by token-row
   conditions; a family-wide UPDATE could miss a row inserted after its
   statement snapshot. Rotation/logout/self-service revoke now share an ordered
   per-user row lock, preserving the fail-closed family invariant.
5. Rejected self-lockout/last-super-admin/permission-override attempts still
   existed only in process logs despite the execution brief. They now create
   attributable, secret-free rows in the existing `AuditLog` before the domain
   rejection is returned.

Public session references were also increased from 64 to 128 bits, and four
regression tests cover actual HTTP `sid` issuance, immediate access revocation,
mixed-user cookie rejection, and family-count semantics.

## Validation evidence (all run for real on the final reviewed diff)

- `bash scripts/agent-check.sh`: **PASS** (1995 tests collected, single Alembic
  head, dev+prod compose config valid, git whitespace clean).
- Full backend suite, `pytest tests/`: **1975 passed, 20 skipped, 0 failed**
  (the 20 skips are the Postgres-only concurrency suites gated behind admin-DSN
  env vars, incl. the new refresh-family one; up from 16 by the four new
  family-concurrency tests).
- New targeted suites: `test_auth_sessions_and_audit.py` (12) and the updated
  `test_auth_session_security.py` — all passing.
- **Real PostgreSQL refresh-family concurrency**,
  `REFRESH_FAMILY_CONCURRENCY_TEST_ADMIN_URL=… pytest tests/test_refresh_family_concurrency.py`
  against disposable, dropped-afterward databases: **4 passed**, and **stable
  across 4 consecutive runs** (the timing-nondeterministic double-submit test
  asserts the real invariant — never a double-mint; ≤1 usable token). Covers:
  two concurrent refreshes never double-mint; proven replay revokes the whole
  family; use-successor racing reuse-parent is fail-closed; session-revoke
  racing a refresh never revives the session.
- **Step-up + Super Admin concurrency regression** on live PostgreSQL:
  **5 passed** (`3/3` step-up + `2/2` Super Admin), unchanged.
- Isolated Postgres migration cycle `upgrade → downgrade → upgrade`: clean;
  backfill verified with real legacy rows (3 → 3 distinct families); disposable
  databases dropped.
- `alembic heads`: single head, `b8f4d2a19c07`.
- `pnpm --filter el-kheima type-check`: **passed**, zero errors.
- `pnpm --filter el-kheima build`: **passed** (pre-existing >500 kB chunk
  warning only). Both locale JSON files parse.
- `git diff --check`: clean.
- During acceptance, the local development database (not production) was also
  advanced forward to `b8f4d2a19c07`; the destructive downgrade/re-upgrade
  rehearsal itself ran only on a separately named disposable database, which
  was dropped afterwards.
- `ruff`/`mypy` are not configured repo gates here and are **not** claimed as run.

## Changed / new files

Modified (backend): `app/core/deps.py`, `app/core/kernel/auth/service.py`,
`app/core/kernel/auth/router.py`, `app/core/kernel/auth/step_up.py`,
`app/core/kernel/models/user.py`, `app/core/rate_limit.py`,
`app/modules/core/services.py`, `tests/test_api/test_auth_session_security.py`,
`tests/test_api/test_super_admin_invariants.py`.

New (backend): `alembic/versions/b8f4d2a19c07_gate_2b3b_refresh_token_families.py`,
`tests/test_api/test_auth_sessions_and_audit.py`,
`tests/test_refresh_family_concurrency.py`.

Modified (frontend): `apps/el-kheima/src/components/StepUpConfirmModal.vue`,
`apps/el-kheima/src/layouts/BackOfficeLayout.vue`,
`apps/el-kheima/src/router/index.ts`, `packages/core/src/api/endpoints.ts`,
`packages/core/src/i18n/locales/ar.json`, `packages/core/src/i18n/locales/en.json`.

New (frontend): `apps/el-kheima/src/views/account/SessionsView.vue`.

Docs: this file, plus `PROJECT_STATUS.md`, `wagdy.md`, and the Project Cockpit
data (`frontend/apps/el-kheima/src/dev/projectCockpitData.ts`,
`frontend/apps/el-kheima/src/views/dev/ProjectCockpitView.vue`) — all updated
only after every command above had already succeeded, and all wording the status
as self-verified/awaiting-review, never accepted.

## Deferred risks (explicit)

1. Access tokens issued before this gate, and POS PIN-switch tokens that have
   no refresh family by design, do not carry `sid`; they retain the existing
   user-global revocation/blacklist and short-TTL behavior. Every real HTTP
   login/refresh issued after this gate is session-bound.
2. Cross-tab simultaneous refresh of the same cookie can, rarely, trip the
   replay path and log that browser out — the sanctioned security-first
   trade-off; the frontend re-logs in cleanly.
3. Tombstones are reaped only by each user's own bounded cleanup on their next
   rotation (no global sweep) — a dormant account's expired rows linger
   harmlessly until that account next rotates.
4. Out of scope by instruction and untouched: typed settings registry,
   finance-domain step-up, user→branch data model, Super Admin
   manage-other-users'-sessions, QR work.

**Accepted locally. Nothing was pushed. No further product gate was changed by
this implementation diff.**
