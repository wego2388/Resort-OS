# Gate 2B3A — Step-Up Control Plane

**Status: مُنفَّذة ومُعتمَدة نهائيًا بعد مراجعتين مستقلتين** (implemented
and finally accepted after two independent review rounds). Implemented
on branch `gate-2b3-step-up-control-plane`, based on checkpoint `75d09e3`.
**Not pushed.** The final acceptance evidence is recorded at the end of
this document.

**Date:** 2026-07-18 (initial implementation, review corrections, and final
Codex acceptance)

## Codex independent review round 1 — Changes Requested, then corrected

An independent Codex review of the initial implementation returned
**Changes Requested**: 2 High findings and 3 Medium findings. All five were
verified against the actual code (not taken on trust) before any fix, and
all five were confirmed real. All five are now fixed, tested, and verified
below. **This round of fixes has not itself been re-reviewed by Codex yet**
— the status above reflects that explicitly.

### High #1 — global-setting fallback leak (confirmed, fixed)

`GET /settings/{key}?branch_id=X` called `crud.get_setting()`, which
silently falls back to the `branch_id IS NULL` (global) row whenever no
branch-specific row exists — even though the branch-ownership check
(`_require_branch_or_global_read`) had already verified the *requested*
branch belonged to the caller. A branch manager asking for their own real
branch's copy of a key that only exists globally received `200` with the
global value, `branch_id: null` and all. Reproduced directly before fixing.

**Fix:** new `crud.get_setting_exact()` — identical lookup, no fallback.
`GET /settings/{key}` now uses it exclusively; the fallback-including
`crud.get_setting()` remains for internal callers only (`get_setting_value()`,
used by beach pricing etc.). `services.upsert_setting()`'s "old value" audit
computation had the identical leak (via the same fallback function) and was
fixed the same way, so `AuditLog` no longer records a global value as if it
were a branch's prior state.

**New test:** `test_manager_does_not_receive_global_fallback_for_own_branch`
— asserts `404`, not a leaked `200`.

### High #2 — TOCTOU race after step-up consumption (confirmed, fixed)

`grant_permission()`, `revoke_permission()`, and `upsert_setting()` trusted
the actor identity resolved once at the *start* of the HTTP request (via
the `Depends(get_super_admin_user)`/`get_admin_user` FastAPI dependency)
without re-verifying it at the moment of the actual mutation. Step-up
inserts a full extra network round trip + commit (`POST /auth/step-up`,
then `consume_step_up()`'s own commit) between that initial check and the
mutation — widening a window that was already narrow before this gate.
Reproduced directly: demoting the actor immediately after step-up
consumption and before `grant_permission()` executed still let the grant
through.

**Fix:** all three functions now re-lock and re-verify the actor
immediately before mutating, using the exact same fixed lock order Gate 2A
already established for `update_user_role()` (`crud.lock_active_super_admins()`
first, then `crud.lock_user_for_update()` for any target row — deadlock-safe
by construction, not a new locking scheme). `grant_permission()` additionally
re-locks and re-checks the *target* isn't `super_admin` at that same instant
(closing the mirror-image race: target promoted to `super_admin` concurrently
with a grant). A new exception, `ActorAuthorizationChangedError` (409
`ACTOR_AUTHORIZATION_CHANGED`), is raised and mapped in all three router
endpoints — generalizes Gate 2A's `ActorSuperAdminPrivilegesChangedError`
beyond the super_admin-only case (`upsert_setting`'s actor can be a
branch-scoped `admin`).

**New tests:** three deterministic single-thread reproductions (actor
demoted/deactivated between step-up and each of the three mutations), plus
a **real PostgreSQL concurrency test**
(`test_promote_target_concurrently_with_grant_permission`) racing a genuine
`update_user_role()` promotion against a genuine `grant_permission()` call
on the same target — verified both possible lock-ordering outcomes are safe
(promotion wins → grant correctly rejected; grant wins → the resulting
override is verified inert per Decision 0003 invariant #1, the same
already-tested "harmless stale override" behavior from Gate 2A).

### Medium — untyped `intent` dict, naive `bool()` coercion (confirmed, fixed)

`POST /auth/step-up`'s `intent` field was read via `dict.get()`/`[]` with
manual `int()`/`str()`/`bool()` casts. `bool("false")` in Python evaluates
to `True` (any non-empty string is truthy) — a client sending
`"allowed": "false"` as a JSON string instead of a JSON boolean would have
silently flipped the intended value. (In practice this didn't enable a
privilege escalation, since the mismatched scope hash would simply fail to
match at consumption time — but it's a real type-safety defect worth fixing
regardless, and was confirmed reachable.)

**Fix:** four new purpose-specific Pydantic models
(`_UserRoleUpdateIntent`, `_PermissionOverrideUpsertIntent`,
`_PermissionOverrideRevokeIntent`, `_SettingUpsertIntent`), each
`extra="forbid"` with real typed fields — `allowed: bool` now goes through
Pydantic's own safe coercion (`"false"` → `False` correctly), not a raw
Python `bool()` call. Malformed/extra-field intents are rejected `422`
before any TOTP/recovery code is touched (verified by test).

**New tests:** `test_string_allowed_value_is_coerced_safely_not_via_naive_bool`
(proves the coercion is now correct, not just "rejected") and
`test_intent_with_unexpected_extra_field_rejected`.

### Medium — unbounded/missing step-up audit logging (confirmed, fixed)

Two gaps: (1) `issue_step_up()` failures (wrong password, wrong/reused
TOTP, etc.) left **zero** `AuditLog` trace — only successful issuance was
logged. (2) `consume_step_up()`'s rejection path logged **every** attempt
unconditionally — an authenticated session (the four protected endpoints
require role auth already, so this is a known-user, not anonymous, actor)
could hammer any of them with a garbage `X-Step-Up-Token` and grow
`AuditLog` without limit, since none of the four protected endpoints carry
rate limiting (only `POST /auth/step-up` issuance does).

**Fix:** new `_log_step_up_issuance_rejected()` appends a secret-free
`step_up_issuance_rejected` row (purpose + reason code only — never the
password/TOTP/recovery value) before each rejection `raise`. Both this and
the existing rejected-consumption logging are now gated behind the
existing `rate_limit()` cache helper (20 audit rows per user per 5 minutes)
— the actual request is still always rejected normally; only the *logging*
of repeated rejections is bounded. This is deliberately still the
authenticated step-up cycle only, not the general anonymous login-failure
audit (still Gate 2B3B).

**New tests:** `test_issuance_failure_now_appends_secret_free_audit_row`,
`test_repeated_invalid_consumption_attempts_are_bounded_not_unlimited`
(30 rejected attempts → fewer than 30 `AuditLog` rows).

### Medium — frontend bilingual-completeness overstatement (confirmed, fixed)

The original report's "full Arabic/English" claim was inaccurate: the
permissions catalog had no English label at all (`PermissionsView.vue`
always rendered `label_ar` regardless of UI language), `SettingsView.vue`
formatted the "last updated" timestamp with a hardcoded `'ar-EG'` locale
regardless of the active language, and both the quick-link labels and the
per-setting technical descriptions were hardcoded Arabic strings with no
i18n key at all.

**Fix:** `PermissionCatalogEntry`/`PermissionCatalogEntryRead` gained a new
`label_en` field (all 21 catalog entries), and `PermissionsView.vue` picks
`label_ar`/`label_en` by current locale. `SettingsView.vue`'s date
formatting now picks `'ar-EG'`/`'en-US'` by current locale; the quick-link
labels and all `SETTINGS_META` descriptions are now full `{ar, en}` pairs.
`AppInput` (shared design-system component, `packages/ui`) gained
`autocomplete`/`inputmode`/`autofocus` pass-through props and a
`defineExpose({ focus })` method — its root is a wrapping `<div>`, so these
attributes and a plain template `ref().focus()` previously landed on the
wrong element (or nowhere). `StepUpConfirmModal.vue` now auto-focuses the
first field on open, sets `autocomplete="current-password"` /
`"one-time-code"` appropriately, and marks its error message
`role="alert" aria-live="assertive"`.

**New test:** `test_catalog_lists_all_entries` extended to also assert
every entry has a non-empty `label_en`.

## Scope and outcome

**This document covers Gate 2B3A only.** Gate 2B3B (unified login-failure
audit logging) and any finance-domain step-up (`finance.close_period`,
`void_payment`) are explicitly out of scope and not started.

## Scope and outcome

Gate 2B3A adds a step-up ("recent auth") control plane in front of the four
most sensitive control-plane mutations already hardened by Gate 2A/2B1/2B2:
role changes, permission-override grant/deny/revoke, and branch/global
settings writes. It also closes a real, separate authorization gap found
while doing this work: `GET`/`PUT /settings*` never verified that the
caller's branch matched the branch being read or written, and never
restricted global (`branch_id=None`) settings to `super_admin`.

A step-up proof is a short-lived, single-use, server-stored, hashed grant
that proves the current session holder re-entered their password (plus a
fresh TOTP code or one recovery code, when 2FA is enabled) for **one exact
operation** — not a general "recently authenticated" flag. The proof is
cryptographically bound to the exact scope of the operation (via a
canonical scope hash) and to the calling session (via the access token's
hash), so it cannot be replayed against a different target, a different
value, or a different browser session, and it cannot be reused a second
time even for the identical request.

## Part 1 — Settings branch/global isolation (fixed first, as required)

Before step-up existed at all, `GET /settings`, `GET /settings/{key}`, and
`PUT /settings/{key}` trusted the client-supplied `branch_id` query
parameter with no server-side ownership check, and treated
`branch_id=None` (global settings) as readable/writable by any manager/
admin respectively.

Fixed via two new shared helpers in `app/modules/core/api/router.py`:

- `_require_branch_or_global_read(db, user, branch_id, action_desc)` —
  `branch_id=None` requires `super_admin`; a real `branch_id` is checked
  against the caller's actual branch via the existing
  `core.services.assert_branch_access()` (super_admin bypass, everyone
  else must match `HR.Employee.branch_id`, fail-closed if unlinked).
- `_require_branch_or_global_write(db, user, branch_id, action_desc)` —
  same branch check; the role floor (`admin+`, `super_admin` for global)
  is still enforced by the route's own `Depends(get_admin_user)`.

`list_settings` tightened to `get_manager_user` (was already manager+).
`get_setting` tightened from `get_current_active_user` (any active
session) to `get_manager_user` — this endpoint had zero frontend callers
(confirmed by search) so the tightening is a pure hardening with no UI
impact.

**Deliberate design decision, documented in code:** a legitimately
branch-scoped request (real `branch_id`, caller's own branch) may still
receive `crud.get_setting`'s existing global-fallback value when no
branch-specific row exists — this preserves `get_setting_value()`'s
internal behavior (used by beach pricing, no-show deadline, etc.) and is
not the same thing as a non-super_admin reaching the global row directly.
Only an explicit `branch_id=None` request is gated to `super_admin`.
Verified directly with a service-level test
(`test_internal_global_fallback_still_works_for_get_setting_value`).

## Part 2 — `step_up_grants` data model

New table via forward migration `ad7ed1e7329b` (`down_revision =
a7c2e91f4b6d`, additive and fully reversible):

```
step_up_grants
  id                  PK
  public_reference    varchar(32)   -- random, non-secret, for audit display
  user_id             FK users(id) ON DELETE CASCADE
  purpose             varchar(64)
  scope_hash          varchar(64)   -- SHA-256 hex of the canonical scope
  token_hash          varchar(64)   UNIQUE  -- SHA-256 of the raw token
  access_token_hash   varchar(64)   -- SHA-256 of the caller's bearer JWT
  assurance_method    varchar(32)   -- "totp" | "recovery_code" | "password_only"
  expires_at          timestamptz
  created_at          timestamptz   server_default now()
  INDEX (user_id)
  INDEX (expires_at)
```

The raw token is a `secrets.token_urlsafe(32)` value, shown to the caller
exactly once in the `POST /auth/step-up` response and never stored or
logged in plaintext — only its SHA-256 is persisted, following the same
pattern already used for `RefreshToken.token_hash`,
`TokenBlacklist.token_hash`, and `TwoFactorRecoveryCode.code_hash`.

TTL: `STEP_UP_TOKEN_TTL_SECONDS` (new `app/core/config.py` field, default
180, `Field(180, ge=60, le=300)` — bounded to the approved 60–300s safe
range). `.env.example` documents the new variable; the real `.env`/
`.env.prod` files were not touched.

Cleanup: both `issue_step_up()` and `consume_step_up()` delete the calling
user's own already-expired grants as a bounded side effect (only that
user's rows, never a global sweep) — issuance always, consumption only on
the success path (so a replay/mismatch probe cannot be used to sweep away
an unrelated still-valid grant belonging to the same account).

## Part 3 — Issuance: `POST /api/v1/auth/step-up`

New endpoint in `app/core/kernel/auth/router.py`, wired to the existing
`AUTH_SENSITIVE_RATE_LIMIT_MAX/WINDOW_SECONDS` bucket in
`app/core/rate_limit.py`. Request body: `current_password` (always
required), `purpose` (one of the four known purposes), `intent` (a dict of
non-secret identifiers — never a raw secret or business value), and
`totp_code` XOR `recovery_code` when 2FA is enabled.

`AuthService.issue_step_up()` enforces, in order:
1. Account must be active.
2. Password must verify.
3. `totp_code` and `recovery_code` together is rejected (`400
   STEP_UP_PROOF_AMBIGUOUS`) — exactly one or the other, never both.
4. If 2FA is enabled: exactly one of a fresh TOTP code or one recovery
   code is required and consumed (shared replay-protection machinery with
   login — `two_factor_last_used_step` for TOTP, conditional `DELETE` for
   recovery codes, both already established in Gate 2B2). Reusing a code
   already consumed by login or a prior step-up call is rejected the same
   way a login replay would be, since it is the identical counter.
5. If 2FA is **not** enabled: a mandatory-2FA role (`super_admin`,
   `accountant`) is refused outright (`403 MANDATORY_2FA_REQUIRED`) — there
   is no password-only path for these roles, ever. A non-mandatory role
   without 2FA gets `assurance_method="password_only"`. (In practice every
   non-`/auth/*` route already blocks a mandatory-role account without
   2FA via `get_current_active_user`; `/auth/step-up` itself intentionally
   uses the lighter `get_current_user` — same as every other `/auth/*`
   route — so this check is the actual primary gate here, not merely
   defense in depth for this one endpoint.)

Response: one-time `step_up_token`, `expires_at`, `assurance_method`.
`Cache-Control: no-store` (via the existing `_mark_sensitive_response()`
helper, same as login/refresh/2FA endpoints). The token never appears in a
URL or query string — it is a JSON body field on the way out and an
`X-Step-Up-Token` header on the way back in.

## Part 4 — Canonical scope binding

`app/core/kernel/auth/step_up.py` is the single source of truth for "does
this proof match this exact operation" — deterministic JSON (`sort_keys`,
no whitespace, `ensure_ascii`) hashed with SHA-256. One builder function
per purpose, imported identically by the issuing endpoint
(`auth/router.py`) and every consuming endpoint
(`modules/core/api/router.py`), so the two sides cannot drift:

- `user_role_update_scope(user_id, role, is_active, reason)`
- `permission_override_upsert_scope(user_id, resource, action, allowed, branch_id, reason)`
- `permission_override_revoke_scope(permission_id, reason)`
- `setting_upsert_scope(key, branch_id, value, reason)`

A free-text `reason` or a setting's new `value` is hashed into the scope
(`reason_sha256`, `value_sha256`) rather than included in the clear — the
scope document itself, and therefore `step_up_grants.scope_hash`, never
reveals the underlying text. The full `reason` string does appear in
`AuditLog` on success (see Part 7) — the constraint is specifically that
**`step_up_grants` never stores the reason or the setting value**, only a
digest as part of the scope hash.

## Part 5 — Consumption

All four protected endpoints receive the proof via `X-Step-Up-Token`
only — never body or query string. A shared router-level helper,
`_consume_step_up_or_raise()`, translates the outcome to HTTP:

- Missing header → `428 STEP_UP_REQUIRED`.
- Any other failure (invalid, expired, replayed, wrong user, wrong
  session, wrong purpose, wrong scope) → `403 STEP_UP_INVALID` with an
  identical generic message in every case — the caller cannot distinguish
  *why* a proof was rejected.

There is deliberately **no** generic "just check purpose" dependency.
Each of the four endpoints builds its own scope hash from the real
path/body payload it just parsed, then calls
`_consume_step_up_or_raise()`, then calls its service function — so the
scope binding is always derived from what the endpoint is actually about
to do, not from a pre-declared shape.

`AuthService.consume_step_up()` is the atomicity boundary: a single
conditional `DELETE ... WHERE token_hash = :t AND user_id = :u AND
purpose = :p AND scope_hash = :s AND access_token_hash = :a AND expires_at
> now()`. Only that statement's own affected-row-count decides
success — a `SELECT` immediately before it exists solely to read the
matched row's `public_reference`/`assurance_method` for the caller's own
audit entry (captured into local variables **before** the method's own
`commit()`, not read from the ORM object afterward — see "Bug found and
fixed" below), and does not weaken the atomicity guarantee. Verified under
real concurrent PostgreSQL transactions (see Validation evidence).

**Transaction boundary — explicitly not one atomic transaction spanning
both steps.** `consume_step_up()` commits its own transaction immediately.
The business mutation that follows (`services.update_user_role()`,
`grant_permission()`, `revoke_permission()`, `upsert_setting()`) is a
**separate** commit on the same session, because those services already
manage their own internal transactions and commits, and nesting step-up
consumption inside them cleanly would require a broader refactor out of
scope for this gate. Consequence, stated plainly: if the business mutation
fails *after* a successful step-up consumption, the proof is already gone.
The UI does not retry — it requests a brand-new proof (see Part 8).

Each protected endpoint re-checks the current, fresh state at execution
time inside its own service call (target user's current role/is_active,
target permission's current existence) — the step-up grant proves *who is
asking*, not that the requested change is still valid; it is not an
authorization cache.

## Part 6 — Protected operations

Exactly these four, and no `GET` endpoint:

| Endpoint | Purpose | New required field |
|---|---|---|
| `PATCH /users/{user_id}/role` | `user_role_update` | `reason` |
| `POST /permissions` | `permission_override_upsert` | `reason` |
| `DELETE /permissions/{permission_id}` | `permission_override_revoke` | typed JSON body `{reason}` |
| `PUT /settings/{key}` | `setting_upsert` | `reason` |

`reason` is enforced as mandatory, real text (`_validate_reason()`:
trimmed, 3–500 chars) at the Pydantic schema layer for all four HTTP
contracts. It is **optional** (default `None`) at the underlying
`services.*` function signatures specifically so existing direct
service-level test calls that bypass the HTTP layer (e.g.
`test_super_admin_concurrency.py`, one call in
`test_auth_bootstrap_recovery.py`) did not need modification — those
calls never went through the HTTP contract this gate changes.

`DELETE /permissions/{permission_id}` now takes a typed JSON request body
(`PermissionRevokeRequest{reason}`) rather than a bare path parameter —
confirmed working with Axios via `api.delete(url, { data: {...},
headers: {...} })` and covered by an HTTP-level test
(`test_revoke_still_allows_cleanup_of_legacy_super_admin_override`, and
the new dedicated step-up test suite).

Every successful mutation's existing `AuditLog` entry (no new table, no
new columns — Gate 2B3A explicitly forbids a parallel audit schema) gains,
inside the existing `old_data`/`new_data` JSON text columns via a new
shared `_step_up_audit_context()` helper: `reason`, `step_up_public_reference`,
`assurance_method`, and `request_id` (via the existing
`app.core.kernel.correlation` context var) when available. Actor, target,
before/after state, and branch context were already present in these
entries from Gate 2A/1B and are unchanged. No password, TOTP code,
recovery code, or step-up token ever appears in any of these fields —
verified directly by a dedicated test that greps every `AuditLog` row
after a full issue→consume cycle.

## Part 7 — Step-up audit (this slice only)

`AuthService` appends two kinds of secret-free `AuditLog` entries within
`app.core.kernel.auth.service`: `step_up_issued` (on successful issuance,
with `purpose`/`assurance_method`/`public_reference`) and
`step_up_consumed`/`step_up_rejected` (on every consumption attempt,
success or failure, for a known authenticated user — `consume_step_up`
always knows `user_id` from the current session even when the grant
lookup itself fails). Unbounded logging of anonymous login-failure
attempts is explicitly **not** implemented here — deferred to Gate 2B3B
per the standing decision that unbounded anonymous-email logging risks
database amplification and PII noise.

## Part 8 — Frontend

New component `frontend/apps/el-kheima/src/components/StepUpConfirmModal.vue`.
Deliberately does not import or structurally resemble `PinGuardModal.vue`
— that component collects a *different manager's* PIN approval and never
itself calls a network endpoint; this component confirms the *current
user's own* identity and itself performs the two-call flow (`POST
/auth/step-up`, then hands the resulting token back to the caller). Both
reuse only the shared `AppModal`/`AppInput` design-system components.

Behavior implemented per spec:
- Full Arabic/English via `useI18n()` (`backoffice.stepUp.*`,
  `backoffice.permissions.*`, `backoffice.settings.*` — new namespaces in
  both `packages/core/src/i18n/locales/ar.json` and `en.json`, kept in
  parity and validated as parseable JSON).
- No forced `dir="rtl"` anywhere in the new component or the two rewritten
  views — direction is inherited from `document.documentElement`/`<body>`
  exactly like `AppModal.vue` and `PinGuardModal.vue` already do (removing
  the `dir="rtl"` that `PermissionsView.vue`/`SettingsView.vue` previously
  hardcoded on their own root element was itself a pre-existing
  inconsistency with the documented bilingual-mode approach, Decision
  0002).
- Reason field, current-password field, and a TOTP-or-recovery-code toggle
  (shown only when `auth.user?.two_factor_enabled` is true) with loading/
  error/focus states.
- `current_password`/`totp_code`/`recovery_code`/`step_up_token` never
  written to `localStorage`/`sessionStorage` — all four live only in
  component-local `ref`s, cleared immediately after use (submitted, or
  handed off via the `confirmed` emit), mirroring the existing
  `access_token`/`pendingEnrollmentToken` in-memory-only pattern already
  documented in `useAuthStore`.
- `2FA_CODE_INVALID` (which the backend deliberately returns identically
  for "wrong code" and "already-used code") is surfaced as one message
  telling the user to wait for the next authenticator code and retry.
- On the retried business mutation coming back `STEP_UP_INVALID`, the
  calling view passes a fresh `error-message` prop back into the modal,
  which resets its sensitive fields and asks for a new confirmation — it
  does **not** automatically resend the mutation.

Integrated into both `PermissionsView.vue` (grant/deny/revert-to-default)
and `SettingsView.vue` (save existing / create new) — both screens'
mutating calls previously sent no `reason` at all and would already have
been rejected by the backend even before this frontend change landed;
this integration is what makes them work again, not an optional
enhancement.

`PermissionsView.vue` now filters `super_admin` out of its own
`targetableUsers` list client-side (Decision 0003 invariant #2) rather
than relying solely on the backend's `409
SUPER_ADMIN_PERMISSION_OVERRIDE_FORBIDDEN` rejection.

Every user-facing string touched in both screens (headings, buttons,
toasts, empty/error states, role and module labels) was converted to
`t('backoffice.permissions.*')`/`t('backoffice.settings.*')` i18n keys.
`SETTINGS_META`'s per-key technical descriptions (which reference actual
function/file names) were deliberately left as Arabic code-adjacent
documentation, not translated UI chrome — consistent with how the rest of
that dictionary already worked.

**`/auth/me` branch_id — minimal fix only, as explicitly instructed.**
`User` (kernel model) has no `branch_id` column at all — confirmed by
reading the model directly; this is a real, larger, deliberately deferred
data-model decision (CLAUDE.md §18), not something this gate can or should
invent a fix for. `useAuthStore.branchId`'s existing `?? 1` fallback was
**not** changed — changing it would ripple into ~30 other call sites
across the app (`SalesDashboardView`, `DiningMenuView`, `BeachPOSView`,
etc.), which the task explicitly said not to do. The only change is
localized to `SettingsView.vue`: a new `hasRealBranchContext` computed
checks `auth.user?.branch_id != null` directly (bypassing the `?? 1`
fallback) and renders a visible amber warning banner when false,
explaining plainly that the account isn't linked to a real branch and the
settings shown may not reflect it. This does not add a new security
assumption that branch is always 1 — it makes the existing, unavoidable
assumption visible instead of silent.

## Bug found and fixed during implementation

`AuthService.consume_step_up()`'s original draft read the matched grant
row via a plain `SELECT` immediately before the atomic `DELETE`, then
after `self.db.commit()` tried to build its return value from
`candidate.public_reference`/`candidate.assurance_method` — accessing
attributes on an ORM object *after* a commit that (by default
`expire_on_commit=True`) expires it, on a row that the same method had
just deleted. This raised `sqlalchemy.orm.exc.ObjectDeletedError` on every
successful consumption, caught by the test suite immediately (multiple
tests failing with a 500 instead of 200/403). Fixed by capturing
`candidate_public_reference`/`candidate_assurance_method` into plain local
variables **before** the commit, and building the return dict from those
instead of the (by then invalid) ORM object. This does not change the
atomicity guarantee — the `SELECT`'s data was never what decided
success/failure, only the `DELETE`'s row count was.

## API compatibility

- `PATCH /users/{user_id}/role`, `POST /permissions`: now require `reason`
  in the body and `X-Step-Up-Token` in the header. Existing callers
  without both will get `422` (missing `reason`) then `428`
  (`STEP_UP_REQUIRED`) once `reason` is added. This is an intentional
  breaking change to a control-plane-only, super_admin-only surface.
- `DELETE /permissions/{permission_id}`: now requires a JSON body
  (previously bodyless) and the same header.
- `PUT /settings/{key}`: now requires `reason` and the header; `GET
  /settings`/`GET /settings/{key}` now additionally enforce real branch
  ownership and restrict `branch_id=None` to `super_admin` (previously
  trusted the query parameter outright).
- `POST /api/v1/auth/step-up` is new.
- No other endpoint's contract changed.

## Migration and rollback notes

`ad7ed1e7329b` (`down_revision = a7c2e91f4b6d`) only creates
`step_up_grants` and its two indexes — no existing table, column, or data
is touched. `downgrade()` drops the table and indexes cleanly. Exercised
end-to-end on a disposable PostgreSQL database: full upgrade from scratch
→ downgrade to `a7c2e91f4b6d` → re-upgrade to `ad7ed1e7329b` → table
structure re-verified (`information_schema.columns`, `pg_indexes`) —
database dropped afterward. See Validation evidence for exact output.

## Deferred risks (explicit, not silently dropped)

1. Gate 2B3B (unified login-failure/lockout audit logging) is untouched,
   per the explicit instruction that unbounded anonymous-email logging is
   a separate risk requiring its own design.
2. `finance.close_period`/`void_payment` step-up and a typed settings
   registry were explicitly named as out of scope; recorded here as
   future work, not implemented.
3. No Super Admin Control Center screen, no session-management-for-another-
   user feature, no role-change screen in the frontend (backend is
   protected and the modal is purpose-built for reuse; no caller wired up,
   as instructed).
4. The `User`→branch data-model gap (no real `branch_id` on `User`) is
   still open; `SettingsView.vue`'s new warning banner makes it visible,
   it does not resolve it.
5. `step_up_grants` accumulates rows for a user's own expired grants until
   that same user's next issuance/consumption call — there is no global
   periodic sweep (matches the explicitly bounded-cleanup design; a
   dormant account's abandoned expired grants are cheap, small rows that
   simply never get swept, not a security issue since `expires_at` is
   still enforced on every read).

## Validation evidence

All commands below were run for real by the implementer in this session,
on this branch, against this diff. This section covers **round 2**
(post-Codex-review corrections); round 1's numbers are preserved in the
Git history of this file for comparison.

- `bash scripts/agent-check.sh`: **PASS**.
- Targeted suite (`test_step_up_control_plane.py`,
  `test_super_admin_invariants.py`, `test_permissions.py`,
  `test_core_http.py`, `test_auth_session_security.py`,
  `test_auth_2fa_http.py`, `test_auth_bootstrap_recovery.py`,
  `test_auth_security_http.py`), `-v`: **170 passed, 0 failed**.
- Full backend suite, `pytest tests/ -v`: **1958 passed, 16 skipped, 0
  failed** (skips are the pre-existing Postgres-only concurrency tests
  across the codebase, all intentionally gated behind admin-DSN env
  vars — one more skip than round 1 because of the new
  `test_promote_target_concurrently_with_grant_permission` concurrency
  test, itself run and passing below).
- Real PostgreSQL concurrency, `STEP_UP_CONCURRENCY_TEST_ADMIN_URL=...
  pytest tests/test_step_up_concurrency.py -v` against a disposable,
  dropped-afterward database: **3 passed** — the original two-thread
  atomic-consumption race (exactly one winner, row fully deleted
  afterward) and sequential-reuse test, plus the new
  `test_promote_target_concurrently_with_grant_permission` (actor
  promotion racing a permission grant on the same target user — both
  possible lock-ordering outcomes verified safe: rejection when the
  promotion wins, provably inert override when the grant wins).
- `alembic heads`: single head, `ad7ed1e7329b` (unchanged — the Codex-review
  fixes were all code-level, no new migration).
- Full migration cycle on a fresh disposable, dropped-afterward PostgreSQL
  database: upgrade from scratch through all prior migrations to head →
  downgrade to `a7c2e91f4b6d` → re-upgrade to `ad7ed1e7329b` — all clean.
- `pnpm --filter el-kheima type-check`: **passed**, zero errors (includes
  the new `AppInput` `defineExpose`/pass-through-prop changes).
- `pnpm --filter el-kheima build`: **passed** (same pre-existing i18n
  dynamic/static dual-import and >500kB chunk warnings only, unrelated to
  this change).
- `git diff --check`: clean, no whitespace errors.
- `git status --short --branch`: on `gate-2b3-step-up-control-plane`,
  matches the file list below exactly.

### Changed files

Final `git diff --stat` (tracked files, after both implementation and the
Codex-review round-1 corrections):

```
 PROJECT_STATUS.md                                  |  61 ++++-
 backend/.env.example                               |   4 +
 backend/app/core/config.py                         |   5 +
 backend/app/core/kernel/auth/router.py             | 153 ++++++++++-
 backend/app/core/kernel/auth/service.py            | 255 +++++++++++++++++++
 backend/app/core/kernel/models/user.py             |  39 +++
 backend/app/core/rate_limit.py                     |   4 +
 backend/app/modules/core/api/router.py             | 219 +++++++++++++++-
 backend/app/modules/core/crud.py                   |  26 ++
 backend/app/modules/core/permission_catalog.py     |  24 ++
 backend/app/modules/core/schemas.py                |  62 ++++-
 backend/app/modules/core/services.py               | 142 ++++++++++-
 backend/tests/conftest.py                          |  79 +++++-
 .../tests/test_api/test_auth_session_security.py   |  15 +-
 backend/tests/test_api/test_core_http.py           |  53 ++--
 backend/tests/test_api/test_permissions.py         |  74 ++++--
 .../tests/test_api/test_super_admin_invariants.py  | 227 ++++++++++-----
 docs/decisions/0003-super-admin-control-plane.md   |  24 +-
 .../apps/el-kheima/src/dev/projectCockpitData.ts   |  20 +-
 .../el-kheima/src/views/admin/PermissionsView.vue  | 228 ++++++++++++-----
 .../el-kheima/src/views/admin/SettingsView.vue     | 279 +++++++++++++++------
 .../el-kheima/src/views/dev/ProjectCockpitView.vue |   8 +-
 frontend/packages/core/src/api/endpoints.ts        |   2 +
 frontend/packages/core/src/i18n/locales/ar.json    |  98 ++++++++
 frontend/packages/core/src/i18n/locales/en.json    |  98 ++++++++
 frontend/packages/ui/src/components/Input.vue      |  19 +-
 wagdy.md                                           |  76 +++++-
 27 files changed, 2006 insertions(+), 288 deletions(-)
```

New (untracked) files:

```
backend/alembic/versions/ad7ed1e7329b_gate_2b3a_step_up_grants.py
backend/app/core/kernel/auth/step_up.py
backend/tests/test_api/test_step_up_control_plane.py
backend/tests/test_step_up_concurrency.py
docs/audits/gate-2b3a-step-up-control-plane.md
frontend/apps/el-kheima/src/components/StepUpConfirmModal.vue
```

## Documentation updated (after validation succeeded, not before)

`PROJECT_STATUS.md`, `wagdy.md`, `docs/decisions/0003-super-admin-control-plane.md`,
and the Project Cockpit snapshot data
(`frontend/apps/el-kheima/src/dev/projectCockpitData.ts`,
`frontend/apps/el-kheima/src/views/dev/ProjectCockpitView.vue`) all say
"تصحيحات جولة مراجعة Codex الأولى منفَّذة، بانتظار مراجعة Codex نهائية"
(round-1 corrections implemented, awaiting final Codex review) — never
"معتمدة نهائيًا" (finally accepted). All were updated only after every
validation command above had already succeeded, per the explicit
instruction not to write status before proof.

## Final independent acceptance — Codex review round 2

The corrected diff was independently reviewed directly rather than accepted
from the implementation report. The global-setting exact lookup, actor and
target reauthorization locks, bounded step-up audit behavior, bilingual UI,
and purpose-bound token flow were rechecked. No remaining Critical, High, or
Medium finding was confirmed inside this gate.

Two small corrections were made during the final review before acceptance:

1. Purpose-specific intent contracts now reject unknown roles, string
   booleans, invalid identifiers, and invalid reasons before consuming a TOTP
   or recovery code.
2. The shared `AppInput` now programmatically associates labels and errors
   with its real input element (`for`/`id`/`aria-describedby`).

Independent final evidence:

- `bash scripts/agent-check.sh`: PASS; 1,975 tests collected;
- focused backend security/control-plane tests: PASS;
- complete backend suite: **1,959 passed, 16 skipped, 0 failed**;
- live PostgreSQL step-up concurrency suite: **3/3 passed**;
- Alembic: one head (`ad7ed1e7329b`); the implementer also completed the
  isolated upgrade/downgrade/upgrade cycle before final review;
- `pnpm --filter el-kheima type-check`: PASS;
- `pnpm --filter el-kheima build`: PASS (pre-existing non-blocking chunk-size
  warning only);
- `git diff --check`: clean;
- Ruff was not available in the backend virtual environment and is therefore
  not reported as run.

**Acceptance decision:** Gate 2B3A is closed and accepted. This decision is
limited to the step-up control-plane slice and is not a production-readiness
claim for the whole platform. Gate 2B3B, finance-domain step-up, typed
settings, and the real user-to-branch data model remain separate work.
