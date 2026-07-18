# Decision 0003: Super Admin Control Plane and Safety Invariants

- **Status:** Accepted product direction; implementation not yet complete
- **Date:** 2026-07-17
- **Owner:** Mohamed
- **Product:** El Kheima Beach Resort OS

## Context

Mohamed approved `super_admin` as the highest trusted application
administrator with complete control over users, roles, permissions, and safe
system configuration. That authority needs one coherent backend policy and one
clear bilingual control center; it must not be assembled from scattered role
checks and free-form settings screens.

The current backend gives `super_admin` role level 100 and already protects a
number of permission and user-management operations. It also has detailed
permission records and mandatory 2FA enrollment gates. The initial read-only
audit nevertheless found important gaps: an explicit permission denial can
currently override role fallback, permission overrides can target a super
admin, user-role mutation does not yet guarantee protection for the current or
last active super admin, login-time TOTP enforcement is configurable but off by
default, and the settings UI accepts arbitrary keys even though only a small
subset has proven live behavior. The staff frontend also does not consistently
load effective permissions from `/permissions/me`.

This record defines the approved security model. It does not claim those gaps
have been fixed.

## Meaning of complete control

`super_admin` has permanent application-level authority to:

- manage staff accounts, activation, roles, and session revocation;
- view the permission catalog and effective authorization;
- manage explicit permission grants/denials for eligible non-super-admin users;
- manage validated global and branch settings within the application's safe
  settings registry;
- inspect security and audit information allowed by retention policy;
- perform administrative recovery and operational oversight exposed by
  reviewed application workflows.

Complete control does **not** mean permission to:

- bypass financial balancing, idempotency, transaction, or state-machine
  invariants;
- silently edit posted orders, payments, journals, payroll, or historical
  records;
- erase or rewrite audit history;
- reveal stored passwords, tokens, encryption keys, card data, or environment
  secrets;
- run arbitrary SQL, shell commands, or filesystem operations from the UI;
- cross a destructive-data or irreversible-operation approval gate.

Those limits protect the resort and apply even to a super admin.

## Accepted authorization invariants

1. An active `super_admin` passes all application permission checks. An
   explicit user-level deny cannot remove super-admin authority.
2. The API rejects creation or modification of permission overrides whose
   target is a `super_admin`.
3. Routine account APIs prevent a super admin from accidentally deactivating or
   demoting their own active account.
4. The system must always preserve at least one active super admin. Demotion,
   deactivation, deletion, bulk updates, imports, and future admin tools enforce
   this invariant transactionally and safely under concurrency.
5. Role/status changes revoke affected sessions and create an attributable
   audit event. Permission changes take effect predictably and invalidate any
   relevant authorization cache.
6. Fixed built-in roles remain the initial model. A dynamic role builder is not
   introduced without a separate business requirement and migration design.
7. The frontend consumes effective permissions to shape navigation and
   controls, but backend authorization remains the only security boundary.
8. A super admin may manage other eligible users but cannot use ordinary
   workflows to turn off the safeguards in this record.

## Authentication requirements

- Super-admin TOTP must be an actual login factor in production, not only an
  enrollment requirement. Production configuration must fail closed if the
  approved login-time enforcement is absent or invalid.
- High-risk mutations such as role changes, permission changes, global-setting
  changes, and sensitive session actions require a server-validated recent
  authentication/step-up proof appropriate to the existing auth architecture.
- Recovery codes, reset paths, and bootstrap procedures must be documented and
  auditable. They must not create a hidden password-only bypass.
- The resort should operate with at least two named super-admin accounts, each
  with separate credentials and 2FA. The system must not silently create these
  production accounts; Mohamed controls provisioning.
- Shared super-admin credentials are prohibited.

## Settings ownership and safety

Settings are separated into three scopes:

1. **Personal preferences** — language and other non-sensitive user choices;
   each employee may update their own supported values.
2. **Branch operational settings** — validated operational configuration;
   delegated only through an explicit permission and branch scope.
3. **Global system settings** — validated resort-wide behavior; writable only
   by `super_admin` with step-up authentication.

A typed server-side registry defines each supported setting's key, type,
validation, scope, read visibility, default, whether it is live or requires a
restart, and whether it is auditable. Arbitrary free-form keys are not accepted
as trusted runtime configuration.

Secrets remain in environment/secret management. The settings API and UI never
return secret values or imply that a masked secret can be recovered. Settings
that are not wired to runtime behavior must not be presented as if they are
active.

## Bilingual Super Admin Control Center

The staff application will provide an Arabic/English, RTL/LTR-safe control
center containing focused areas for:

- users, activation status, roles, and session revocation;
- permission catalog, explicit overrides, and an effective-access preview;
- typed global and branch settings with clear scope and restart/live status;
- security posture, 2FA state, and recent sensitive events;
- searchable, read-only audit activity with actor, target, reason, request, and
  time context.

Dangerous actions use clear consequences, recent-authentication checks, reason
capture where appropriate, and confirmation patterns from the central design
system. The screen does not expose arbitrary database, environment, or server
controls.

## Controlled implementation sequence

1. Write tests that reproduce the current authorization and lockout gaps.
2. Fix backend super-admin invariants, permission semantics, concurrent
   last-active-super-admin protection, session revocation, and audit events.
3. Enforce production login-time TOTP and add a reusable server-side step-up
   policy for the approved sensitive actions.
4. Replace unsafe free-form settings behavior with the typed, scoped registry
   and migrate existing supported values without deleting unknown data.
5. Make the frontend load effective permissions and build the bilingual control
   center on the reviewed APIs.
6. Perform an independent security/authorization review and run the complete
   affected backend and frontend validation gates.

Each phase is a separate reviewable diff. Database changes, if required, use
forward migrations and include rollback/data-impact reasoning.

## Required tests and acceptance criteria

- Explicit deny cannot remove an active super admin's authority.
- Permission overrides targeting a super admin are rejected.
- Self-demotion/self-deactivation is rejected by routine APIs.
- The last active super admin remains protected under concurrent requests.
- Role/status/permission changes revoke or refresh affected authorization and
  produce complete audit events.
- An ordinary admin cannot change global settings or elevate themselves.
- Delegated branch settings cannot escape the actor's branch and permission
  scope.
- Unsupported, wrong-type, secret, or read-only setting mutations are rejected
  safely.
- A normal active user cannot discover restricted setting values.
- Production super-admin login requires valid TOTP and sensitive mutations
  reject stale or missing step-up proof.
- The control center shows effective access accurately in Arabic RTL and
  English LTR, while direct API attempts remain protected independently.
- Existing supported settings and user access remain backward-compatible or
  receive an explicit migration/compatibility plan.

## Current status

The direction remains approved and is now partially implemented in isolated
gates:

- Gate 2A is accepted: permission semantics, self-lockout, last-active-admin,
  and concurrent role-change invariants are enforced.
- Gate 2B1 is accepted: password/session lifecycle, atomic refresh rotation,
  and local TOTP QR generation are enforced.
- Gate 2B2 is accepted: production TOTP is fail-closed, privileged bootstrap
  has no static production password, enrollment uses a separate expiring
  token, temporary credentials are restricted, and TOTP/recovery codes are
  single-use. Independently re-verified: full backend suite, 3 real-Postgres
  concurrency proofs, and a full migration upgrade/downgrade/upgrade cycle.
- Gate 2B3A: **مُنفَّذة ومُعتمَدة نهائيًا** (implemented and finally
  accepted after two independent Codex review rounds): reusable,
  purpose-bound, single-use step-up proofs
  now gate `PATCH /users/{id}/role`, `POST /permissions`, `DELETE
  /permissions/{id}`, and `PUT /settings/{key}`, each requiring a
  mandatory `reason`. Settings branch/global isolation was also fixed in
  the same slice (real branch ownership checks, global settings restricted
  to `super_admin`). An independent Codex review of the initial
  implementation returned Changes Requested (2 High + 3 Medium findings —
  a settings-fallback branch leak, a TOCTOU actor/target re-authorization
  race, an untyped intent contract, unbounded/missing step-up audit
  logging, and an overstated bilingual-completeness claim); all five were
  confirmed against the code and fixed, with new regression and real-
  Postgres concurrency tests. The corrected diff then passed final
  independent review: 1,959 backend tests, 3/3 live-Postgres step-up
  concurrency tests, frontend type-check/build, and a clean diff check.
- Gate 2B3B is **implemented and finally accepted**: bounded secret-free auth
  auditing, refresh-token families with atomic replay detection, immediate
  session-bound access revocation (`sid`), and bilingual self-service session
  management all passed independent review. The review also closed mixed-user
  cookie ownership, family revoke/rotation serialization, distinct-family
  counting, and rejected control-plane audit gaps. Final evidence: 1,975
  backend tests, 4/4 live-Postgres refresh-family concurrency tests, 3/3
  step-up and 2/2 Super Admin concurrency regressions, migration cycle, and
  frontend type-check/build.
- The typed settings control center remains future work. It was deliberately
  excluded from the identity/session gate and must not be treated as complete.

See `docs/audits/gate-2a-super-admin-invariants.md`,
`docs/audits/gate-2b1-auth-session-lifecycle.md`,
`docs/audits/gate-2b2-totp-bootstrap-recovery.md`, and
`docs/audits/gate-2b3a-step-up-control-plane.md`, plus
`docs/audits/gate-2b3b-auth-audit-session-defense.md`. None of these gates alone
is a claim that the complete platform is production-ready.
