# Task Brief: <short outcome>

> Copy this file for a real task, or fill the same sections in the approved
> prompt. Keep one brief per bounded phase.

## Control

- **Status:** draft | approved | implementing | under review | accepted
- **Owner:** Mohamed
- **Implementation engineer:** Claude Code
- **Independent reviewer:** Codex
- **Base commit:** `<explicit commit SHA>`
- **Branch/worktree:** `<name and path>`

## Product outcome

In plain language, what should become safer, faster, or newly possible for a
guest or employee?

## Current evidence

- Existing implementation found:
- Reusable models/services/components:
- Root cause or gap:
- Relevant files and tests:

Do not fill this section from memory. Link it to inspected code and test
evidence.

## Confirmed decisions

- Decision:
- Decision:

## Assumptions

- Assumption, why it is safe, and how it will be validated:

## Scope for this phase

- Included:
- Included:

## Explicitly out of scope

- Deferred item and reason:
- Deferred item and reason:

## Invariants

### Data and finance

- What must always remain true?
- What is immutable and how are corrections represented?
- What transaction, lock, uniqueness, or idempotency protection is required?

### Authorization and audit

- Who may perform each sensitive action?
- What server-side scope is enforced (branch/outlet/zone/ownership)?
- Which audit events and actors are required?

### API and compatibility

- Existing contracts to preserve:
- Compatibility or migration adapter:
- Public identifier/security rules:

### UX, Arabic, and accessibility

- Primary user and device:
- Arabic RTL and English LTR behavior:
- Loading, empty, error, offline, and duplicate-submit behavior:

## Expected files

List likely files, clearly marked as an estimate until discovery is complete.

## Migration plan

- Schema/data change:
- Existing-data preservation:
- Upgrade impact:
- Rollback considerations:
- PostgreSQL-specific validation:

Write `none` when no migration is expected.

## Acceptance criteria

Use observable behavior:

1. Given ..., when ..., then ...
2. Unauthorized ..., when ..., then ...
3. Concurrent/retried ..., when ..., then ...

## Validation plan

- Targeted backend tests:
- Full backend suite:
- Frontend type-check/build:
- Migration checks:
- Docker/deployment checks:
- Manual or browser walkthrough:
- Checks intentionally not run, with reason:

## Stop conditions

Stop and ask Mohamed when destructive data loss, production credentials, an
irreversible external action, or a genuinely undecidable business rule is
required.

## Handoff requirements

- Diff summary and important files.
- Exact commands and results.
- Migration/compatibility notes.
- Security, financial, UX, RTL, and accessibility impact.
- Remaining risks and next highest-value phase.
- No commit or push unless explicitly authorized.
