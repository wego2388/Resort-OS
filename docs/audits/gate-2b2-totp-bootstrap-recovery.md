# Gate 2B2 — Secure TOTP Bootstrap and Recovery

**Status: ACCEPTED.** Implemented on `gate-2b2-totp-bootstrap`, independently
reviewed by Claude (full uncommitted diff, not the implementation report taken
on trust), and accepted by Mohamed and Codex. Implementation commit
`c78e7ba28a540a3a6611ff3725d856641699ba6f`. Not pushed to `origin`.

**Date:** 2026-07-18

**This acceptance covers Gate 2B2 only** — the TOTP bootstrap/recovery state
machine described in this document. It is not a claim that El Kheima Beach
Resort OS as a whole is production-ready. See "Remaining risks and next gate"
below, and in particular the production reference-data gap, which is
unresolved.

## Scope and outcome

Gate 2B2 closes the unsafe gap between Gate 2B1's session controls and actual
production TOTP enforcement. It replaces known production bootstrap
credentials and first-enroller ownership with an explicit, out-of-band,
auditable onboarding state machine. It also introduces one-time recovery codes
without making recovery a weaker password-only bypass.

This gate does not implement general recent-auth/step-up proofs for role,
permission, or settings mutations. That remains Gate 2B3.

## Confirmed baseline defects

1. `app.seed` created `admin@resortos.local` with a known hard-coded password
   and eleven known demo identities, including an accountant, in every
   environment where the command was run.
2. The source comment said the password came from environment configuration,
   but the value was actually hard-coded.
3. A mandatory-role account without 2FA could obtain an access token with only
   its password and then let the first holder of that session bind the TOTP
   secret.
4. `LOGIN_2FA_ENFORCED` defaulted to false and production configuration did not
   fail startup when it remained false.
5. `FIELD_ENCRYPTION_KEY` was optional at configuration validation time even
   though TOTP secret persistence requires a valid Fernet key.
6. There was no forced password replacement state, enrollment token, recovery
   code, or operator bootstrap/recovery command.
7. Binding or disabling a factor relied on an existing access session and a
   TOTP code only; binding did not require password reauthentication.
8. Existing TOTP values could be replayed more than once within their valid
   time window.
9. Promotion to `super_admin` or `accountant` could create an active
   mandatory-role account before 2FA was enrolled.
10. The staff onboarding screen was Arabic-only and did not explain recovery,
    session invalidation, or the temporary-credential lifecycle.

## Approved state machine

The secure bootstrap journey is deliberately explicit:

1. A trusted shell operator runs `python -m app.admin_bootstrap create` for a
   new named super-admin, or `recover` for an existing account.
2. The command generates a random temporary password and a separate 256-bit
   enrollment token. Neither can be supplied as a CLI argument or environment
   variable. The enrollment token is shown once; only its SHA-256 digest and
   expiry are stored.
3. The bootstrap login requires both values and does not receive a refresh
   cookie.
4. The user must replace the temporary password. Every access/refresh session
   is invalidated.
5. A mandatory-role user signs in again with the new password and the same
   unexpired enrollment token, then binds a TOTP authenticator.
6. Successful binding clears the bootstrap token, closes the setup session,
   and displays eight 120-bit recovery codes once.
7. The user confirms the codes were stored separately, then signs in with a
   fresh TOTP code.
8. A recovery code may replace TOTP at login exactly once. Regeneration
   requires both the current password and current TOTP and invalidates all
   prior recovery codes and sessions.

The `recover` command preserves the existing role. It cannot turn a manager,
cashier, or accountant into a super-admin; role changes remain exclusively in
the Gate 2A control plane.

## Backend implementation

### Data model and migration

Forward migration `a7c2e91f4b6d` adds:

- `users.must_change_password`;
- `users.two_factor_bootstrap_required`;
- hashed enrollment token and timezone-aware expiry columns;
- `users.two_factor_last_used_step` for atomic TOTP replay prevention;
- `two_factor_recovery_codes`, with user cascade ownership and a unique
  `(user_id, code_hash)` constraint.

Existing TOTP secrets and account records are preserved. Existing un-enrolled
mandatory-role accounts and known legacy seed identities are marked as
requiring secure bootstrap. The migration does not create, delete, demote, or
deactivate a user.

The migration marker is fail-closed outside the explicit safe environments.
Inside `development/test/testing`, a legacy marker with no provisioned token
does not strand the local demo account: current-password reauthentication can
complete TOTP setup. A real CLI bootstrap remains token-bound in every
environment because it has a temporary-password state and stored enrollment
token hash. Regression tests cover both sides of this boundary.

Recovery codes contain 120 random bits, are formatted for human entry, shown
once, normalized server-side, and stored only as SHA-256 digests. A conditional
database `DELETE` is their one-time concurrency boundary.

### Login and session policy

- Production, staging, and unknown environment names fail startup unless
  `LOGIN_2FA_ENFORCED=true` and `FIELD_ENCRYPTION_KEY` is a valid Fernet key.
- Mandatory-role enrollment and copied legacy seed identities require the
  separate enrollment token before an access token is issued outside the
  explicit local/test environments.
- Bootstrap/incomplete sessions never receive a refresh cookie. Legacy refresh
  rows for incomplete onboarding are rejected and deleted on rotation.
- `must_change_password` blocks every non-auth HTTP route and all WebSocket
  access. `/auth/me` remains available so the UI can render the correct next
  step.
- Password replacement requires the enrollment token when bootstrap is
  active, clears the temporary-password state, revokes all sessions, and keeps
  the enrollment proof only until mandatory TOTP binding finishes.
- TOTP login accepts the authenticator code or one recovery code, never a
  password-only fallback.
- Sensitive authentication responses, including refresh, carry
  `Cache-Control: no-store`.
- Refresh cookies use the same explicit safe-environment allow-list as the
  authentication validator. Staging and unknown environment names receive
  `Secure; SameSite=Strict`, not development cookie settings.
- Password-reset delivery keeps its enumeration-safe public response while
  logging internal delivery failures without the address or bearer token.

### Factor binding, recovery, and replay protection

- Normal TOTP binding requires the current password again. A provisioned
  bootstrap binding requires the independent enrollment token; mandatory
  production accounts reach setup only through that bootstrap flow.
- An in-progress TOTP secret is reused on setup retry rather than silently
  changing the QR while the user is scanning it.
- TOTP enable, disable, and recovery-code regeneration close all sessions.
- Mandatory roles cannot disable TOTP.
- Each accepted TOTP counter is stored through a conditional update. The same
  six-digit value cannot be replayed by a second request in the same 30-second
  time step, including under PostgreSQL concurrency.
- Recovery-code regeneration requires current password plus current TOTP.
- Security-relevant factor, recovery, password, and bootstrap events append
  secret-free entries to the existing `AuditLog`. General login-failure audit
  unification remains deferred.

### Control-plane and seed safeguards

- `app.seed` is now explicitly restricted to
  `development/test/testing`. Production, staging, and mistyped environment
  names fail instead of installing synthetic guests, finance records, and
  known accounts.
- `python -m app.admin_bootstrap create` creates a named super-admin through a
  local interactive control plane with random credentials.
- `python -m app.admin_bootstrap recover` rotates an existing account while
  preserving its role and invalidating its old factor and sessions.
- An active account cannot be promoted or reactivated as `super_admin` or
  `accountant` until 2FA is already enabled.

## Staff frontend

The El Kheima staff app now provides an Arabic/English, RTL/LTR-safe onboarding
journey:

- login understands enrollment-token, authenticator, and recovery-code
  challenges without displaying internal error terminology;
- a dedicated temporary-password screen explains why access is restricted and
  why the session will close;
- the factor-binding screen requires the correct proof, renders the QR locally,
  and supports a manual key without claiming an internet dependency;
- eight recovery codes are displayed once with a copy action and an explicit
  saved-code acknowledgment before returning to login;
- existing users can regenerate codes or, when their role permits, disable 2FA
  only after current-password plus current-TOTP confirmation;
- router and API guards send incomplete users to the correct onboarding step
  instead of letting dashboards fail into empty states.

The enrollment token exists only in Pinia memory for the current page lifetime;
it is never written to local storage or session storage.

## API compatibility

- `/auth/login` keeps the OAuth2 username/password form and existing
  `otp_code`; `recovery_code` and `enrollment_token` are additive fields.
- `/auth/change-password` keeps the Gate 2B1 compatibility alias
  `old_password`; `enrollment_token` is additive and required only for
  bootstrap accounts.
- `/auth/2fa/setup` now requires current-password reauthentication or an
  enrollment token. This is an intentional security tightening.
- `/auth/2fa/enable` returns recovery codes and requires reauthentication after
  success; the old success message remains.
- `/auth/2fa/disable` now requires `current_password` as well as TOTP and closes
  sessions. Older callers must add that field.
- `/auth/2fa/recovery-codes/regenerate` is new.
- `UserRead` adds onboarding-state booleans; no secret/hash/expiry is exposed.

## Migration and rollback notes

The forward migration was exercised on a disposable PostgreSQL database through
full-chain upgrade, Gate 2B2 downgrade, and second upgrade. It is structurally
reversible and does not mutate existing TOTP secrets.

Rollback after users have received recovery codes is operationally lossy: the
codes and bootstrap state would be removed. A rollback therefore requires a
maintenance window, explicit disabling of the new application version, and a
fresh credential/factor recovery plan. Never downgrade while the new backend
is serving requests.

The ignored local production environment file was not edited. An operator must
set `LOGIN_2FA_ENFORCED=true` and a stable Fernet key before the production
process can start. This is an intentional deployment gate, not a hidden
fallback.

## Validation evidence

- focused bootstrap, session, 2FA, configuration, and ETA regression suites:
  passed;
- real PostgreSQL concurrency: refresh rotation, recovery-code consume, and
  TOTP consume all passed with one winner and one rejected replay;
- disposable PostgreSQL migration: full upgrade, downgrade to `9989c0432ccc`,
  and re-upgrade to `a7c2e91f4b6d` passed;
- `pnpm --filter el-kheima type-check`: passed;
- `pnpm --filter el-kheima build`: passed with the pre-existing i18n and bundle
  size warnings only;
- full backend suite: **1,937 collected; 1,924 passed; 13 skipped; 0 failed**;
- `alembic heads`: one head, `a7c2e91f4b6d`;
- `git diff --check`: clean at the validation checkpoint.

## Remaining risks and next gate

1. Reusable purpose-bound recent-auth/step-up proofs for role, permission, and
   global-setting changes remain Gate 2B3.
2. Auth audit coverage is improved for mutations and recovery, but login
   failures/lockouts/reset delivery are not yet fully unified in `AuditLog`.
3. Refresh tokens do not have family identifiers/reuse-family revocation.
4. Access-token cutoff across multiple instances still requires shared Redis;
   the in-memory fallback is not fleet-wide.
5. Recovery delivery and operator identity rely on the trusted shell process;
   no help-desk workflow or hardware-backed recovery process exists yet.
6. Production reference-data initialization is not separated from the old demo
   seed. Production must configure branches and operational reference data
   explicitly; this platform must not be declared production-ready until that
   workflow is validated.
7. The bilingual onboarding UI has type/build validation and backend contract
   tests, but no automated browser accessibility/E2E suite is configured in the
   repository yet.

**Acceptance boundary:** Gate 2B2 may be accepted only after an independent
review verifies the current diff and reproduces the full suite, PostgreSQL
concurrency proofs, migration cycle, and staff production build.

## Independent review and acceptance (2026-07-18)

Claude reviewed the complete uncommitted diff directly (not the implementation
report on trust) and independently reproduced every validation claim above,
including a full upgrade → downgrade → upgrade migration cycle run against a
disposable PostgreSQL database created and dropped for this review:

- targeted suite (`test_auth_bootstrap_recovery.py`,
  `test_auth_session_security.py`, `test_auth_security_http.py`,
  `test_auth_2fa_http.py`): **79 passed**;
- full backend suite: **1,924 passed, 13 skipped, 0 failed**;
- real PostgreSQL concurrency (refresh rotation, recovery-code consume, TOTP
  consume): **3 passed**, exactly one winner and one rejected replay each,
  disposable database dropped afterward;
- migration cycle on a disposable database: upgrade from scratch → downgrade
  to `9989c0432ccc` → re-upgrade to `a7c2e91f4b6d` → all clean, database
  dropped afterward;
- `pnpm --filter el-kheima type-check` / `build`: passed;
- `bash scripts/agent-check.sh` and `git diff --check`: passed.

**Findings: zero Critical, zero High, zero Medium.** Two Low-severity
observations were logged and deliberately deferred, not fixed in this gate:
duplicated `_SAFE_ENVIRONMENTS` allow-list literals across `config.py`,
`service.py`, and `router.py` (identical values in all three, no drift risk
today, worth consolidating later); and `AuthService.verify_refresh_token()`
being dead code with no caller (pre-existing before Gate 2B2, not a
regression).

**Deployment note — not a Gate 2B2 defect:** the real `backend/.env.prod`
still has `LOGIN_2FA_ENFORCED=false`. The new `_validate_production_authentication`
config validator means the backend process will now refuse to start in any
environment other than `development`/`test`/`testing` until an operator sets
`LOGIN_2FA_ENFORCED=true` and confirms `FIELD_ENCRYPTION_KEY` is a valid
Fernet key. This is the intended fail-closed behavior, not a bug — but it is
a **mandatory operational step before the next production restart or
deployment of this branch**, not something the application does silently on
its own. `backend/.env.prod` was not read for its secret values, and was not
edited, by this review.

**Decision:** Gate 2B2 is accepted. This acceptance is scoped to the TOTP
bootstrap/recovery state machine only; see "Remaining risks and next gate"
above for what explicitly remains open, and DEPLOYMENT.md for the required
`.env.prod` update before the next production deploy.
