# Independent Review Template

Review the requested diff without editing files. Read the task brief and
accepted decisions first, then inspect the implementation and relevant tests.

## Scope reviewed

- Base and target:
- Diff/worktree:
- Task brief:
- Areas inspected:
- Checks run:

## Findings

Order findings by **Critical**, **High**, **Medium**, then **Low**. Do not inflate
severity. A finding must be actionable and supported by evidence.

For every finding use:

### `[Severity] Short title`

- **Classification:** introduced regression | pre-existing defect | optional
- **Confidence:** high | medium | low
- **File:** `path/to/file:line`
- **Evidence:** the exact execution path, invariant, test, or contract that
  demonstrates the problem
- **Problem:** what is wrong
- **Impact:** realistic security, financial, operational, compatibility, or UX
  consequence
- **Fix:** smallest safe correction
- **Regression test:** test that should fail before the fix and pass after it

If a line number is not meaningful (for example a missing migration), name the
nearest relevant symbol and files.

## Required review lenses

- correctness and state transitions;
- authentication, authorization, branch/outlet/ownership isolation, and IDOR;
- transaction boundaries, row locks, uniqueness, retries, and idempotency;
- Decimal/rounding, journals, refunds, voids, shifts, and auditability;
- migration safety and backward compatibility;
- public endpoint abuse, token handling, validation, and data exposure;
- API/frontend contract consistency;
- loading/error/offline states, duplicate submission, Arabic RTL, English LTR,
  keyboard/touch use, and accessibility;
- missing negative, concurrent, migration, and regression tests.

## Summary

- Finding counts by severity:
- Must fix before acceptance:
- Correct but deferrable risks:
- Areas not reviewed and why:

If there are no findings, say so explicitly and still list residual risks and
checks that were not run. Never invent a finding to fill the report.
