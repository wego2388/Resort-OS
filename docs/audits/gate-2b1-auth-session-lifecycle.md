# Gate 2B1 — Authentication and Session Lifecycle

**Status:** Implemented by Codex on `gate-2b-authentication-step-up`; pending
independent Claude review and acceptance. No commit or push has been made.

**Date:** 2026-07-18

## Scope

This slice is deliberately limited to password changes/resets, refresh-token
lifecycle, logout, auth rate limits, and removal of the third-party TOTP QR
secret leak. It does not claim to complete Gate 2B or production identity
hardening.

## Confirmed baseline defects

1. `ProfileView.vue` sent `current_password`, while the untyped backend router
   indexed `old_password`; the real UI flow failed with HTTP 500.
2. `admin` and `super_admin` bypassed current-password verification through the
   API.
3. Password change/reset did not invalidate access or refresh sessions.
4. A disabled user could rotate an existing refresh token, and Gate 2A role or
   status changes did not delete refresh sessions.
5. Logout depended on an optional access token in the request body and did not
   consume the server-side refresh token represented by the cookie.
6. Password-reset tokens were stored in plaintext and multiple live links for
   one account remained valid.
7. Refresh rotation deleted and created in separate commits and lacked an
   atomic consume operation, allowing concurrent replay.
8. TOTP setup returned a URL at `api.qrserver.com` containing the complete
   `otpauth://` value. Rendering that image disclosed the permanent TOTP secret
   to a third party.
9. Reset, refresh, and password-change endpoints lacked route-specific limits;
   reset requests also lacked an account-scoped limit.

## Implemented controls

### Password and reset contract

- Replaced loose request dictionaries with typed request models.
- Standardized on `current_password`, while accepting legacy `old_password`
  temporarily. Conflicting values are rejected.
- Every role must prove the current password, and the new password cannot equal
  the existing password.
- Successful change/reset deletes every refresh token for the account in the
  same database transaction and publishes an access-token cutoff after commit.
- Responses explicitly state that reauthentication is required and clear the
  refresh cookie.
- New reset tokens are stored as SHA-256-derived keys, only the newest link for
  an account remains active, and successful use consumes all of them. Existing
  raw tokens retain only their already-defined expiry as a bounded compatibility
  path.

### Refresh and logout lifecycle

- Refresh creation and rotation reject missing or inactive users.
- Legacy refresh rows created before an account cutoff are rejected.
- Rotation conditionally consumes the presented row and creates its replacement
  in one transaction. A concurrent loser cannot mint another token.
- Gate 2A role/status changes delete all target refresh sessions within their
  existing transaction, and publish the access cutoff only after commit.
- Logout derives the access token from the Authorization header, consumes the
  refresh cookie token for the same user, and clears the cookie. The previous
  body token remains a compatibility fallback.
- The staff auth store now waits for the logout response (with a bounded
  timeout) before navigating, so normal browser navigation cannot abort the
  server-side refresh-token revocation request.
- JWT `iat` now retains sub-second precision so a legitimate immediate login
  after revocation is not rejected as if it predated the cutoff.

### TOTP confidentiality

- TOTP QR PNGs are generated in-process using the already-installed `qrcode`
  dependency and returned as data URIs.
- No external image service receives the `otpauth://` value or TOTP secret.

### Abuse controls

- Added explicit limits for refresh, sensitive authenticated auth operations,
  password-reset request/confirm, and a separate hashed-account reset limit.
- Added safe example configuration values to `.env.example`; ignored local
  production environment files were not edited or committed.

## Compatibility and migration impact

- No database migration is required.
- `old_password` remains accepted temporarily for API clients; the staff UI
  uses `current_password`.
- Existing plaintext reset tokens remain usable only until their original
  expiry; newly issued tokens are never stored raw.
- Password change/reset now signs the current browser out and invalidates other
  sessions. This is an intentional security behavior change.
- Disabled users and refresh tokens predating a revocation cutoff now receive
  authentication failure instead of a replacement access token.

## Tests and validation

Implemented regression coverage includes:

- frontend/backend password-field compatibility and conflict rejection;
- current-password verification for ordinary, admin, and super-admin roles;
- access and refresh invalidation after password change/reset and role change;
- successful immediate relogin after a cutoff;
- refresh rotation, replay rejection, inactive-user rejection, and legacy
  cutoff rejection;
- logout of header access token plus cookie refresh token;
- hashed, single-active password reset links and account-scoped throttling;
- internal TOTP PNG generation with no HTTP URL or raw secret;
- route-level auth rate-limit wiring;
- real PostgreSQL concurrent refresh rotation.

Results:

- targeted authentication, 2FA, Gate 2A, and dependency tests: passed;
- full backend suite: **1,914 collected; 1,903 passed; 11 skipped; 0 failed**;
- PostgreSQL concurrency proof: **1 passed**, with exactly one successful
  rotation and one rejected replay; temporary databases removed;
- `pnpm --filter el-kheima type-check`: passed;
- `pnpm --filter el-kheima build`: passed (pre-existing i18n/bundle warnings);
- no Alembic migration was added.

## Deferred risks

These are explicitly outside Gate 2B1 and must remain visible:

1. There is no reusable recent-auth/step-up proof for role, permission, or 2FA
   enrollment changes.
2. Auth-sensitive actions do not yet write the unified immutable audit trail.
3. Production login-time TOTP is not fail-closed. Enabling it must follow a
   safe bootstrap/default-password and account-recovery design.
4. The seeded, documented default super-admin credential is not forced to
   change before TOTP enrollment.
5. Refresh tokens do not yet carry a family identifier, so reuse of an already
   consumed token cannot revoke the legitimate descendant family.
6. Cross-instance access-token cutoffs require shared Redis; the current
   in-process fallback cannot guarantee fleet-wide immediate revocation.
7. Recovery codes, explicit trusted-device policy, and reset-delivery audit or
   observability are not implemented.

## Independent review gate

Before acceptance, Claude must review the complete uncommitted diff rather than
trust this report, reproduce the targeted/full checks, run the PostgreSQL race
test, fix only confirmed defects, and stop before Gate 2B2. Gate 2B1 must then
receive a separate checkpoint so later TOTP/step-up work cannot be mixed into
this security boundary.
