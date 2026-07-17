# Reusable Agent Prompts

Replace angle-bracket placeholders. These prompts do not override `AGENTS.md`,
`CLAUDE.md`, an accepted decision record, or Mohamed's current instructions.

## 1. Claude discovery prompt (no edits)

```text
Work in <worktree path>.

Read AGENTS.md and CLAUDE.md fully, then read the beginning and newest relevant
sections of PROJECT_STATUS.md and every accepted decision related to <task>.

This is a discovery pass only. Do not edit files, create migrations, install
dependencies, commit, push, or change external state.

Inspect the complete existing implementation for <task>, including models,
schemas, CRUD, services, routers, permissions/policies, audit events,
migrations, frontend callers/components/state, real-time behavior, and tests.
Do not create a duplicate design.

Report:
1. Current end-to-end workflow with file/symbol evidence.
2. Root causes and risks, separated into Critical/High/Medium/Low.
3. Reusable code and conflicting/duplicate logic.
4. Data, finance, authorization, concurrency, compatibility, UX/RTL, and test
   impact.
5. A phased plan, with only Phase 1 fully bounded.
6. Expected files and migration strategy.
7. Acceptance criteria and exact validation commands.
8. Business decisions that truly cannot be inferred safely.

Stop after the report and wait for approval.
```

## 2. Claude implementation prompt (one phase)

```text
Implement only approved Phase <number> from <task brief> in <worktree path>.

Before editing, verify the branch/base commit, current status, worktrees, and
the discovery assumptions against the current code. Preserve user-owned work.

Constraints:
- Keep public APIs compatible unless the brief explicitly approves a change.
- Reuse existing architecture and design-system components.
- Do not add dependencies without documented justification.
- Do not delete migrations or existing data.
- Enforce permissions on the backend and audit sensitive actions.
- Use Decimal for money and explicit transactions/locking/idempotency where
  the invariants require them.
- Keep changes focused; do not implement later phases.
- Do not commit or push.

Add regression tests for changed behavior. Run targeted checks while working,
then all checks required by the task brief. Review your own diff for security,
financial, concurrency, compatibility, RTL, accessibility, and error-state
regressions.

At the end show git status, diff stat, important diff details, every validation
command and result, migrations/compatibility impact, assumptions, and remaining
risks. Update wagdy.md in plain Arabic if the project state or an approved
decision changed.
```

## 3. Codex independent review prompt (same worktree, no edits)

```text
Review the current uncommitted changes in <exact Claude worktree> as an
independent Principal Engineer. Read AGENTS.md, the approved task brief, and
relevant accepted decisions first.

Do not edit files, install dependencies, create migrations, commit, push, or
change external state.

Review correctness, security, server-side authorization, branch/outlet/data
isolation, database transactions, locks, race conditions, idempotency,
financial integrity, auditability, backward compatibility, API/frontend
contracts, missing tests, UI/UX regressions, Arabic RTL/English LTR,
accessibility, and network/error behavior.

Use docs/agent-workflow/REVIEW_TEMPLATE.md exactly. Classify each finding as an
introduced regression, pre-existing defect, or optional improvement. Include
file:line, evidence, realistic impact, smallest safe fix, and a regression
test. Sort by Critical/High/Medium/Low. Do not invent findings.
```

## 4. Claude remediation prompt

```text
These are the independent Codex findings for <phase>.

Verify every finding against the current code; do not apply it mechanically.
Classify it as:
- correct and fix now;
- correct but defer, with concrete reason/risk;
- incorrect, with evidence.

Fix only correct in-scope findings. Add or update regression tests, rerun the
task brief's checks, review the new diff, and do not commit or push. Report the
classification table, changes, exact command results, and residual risks.
```

## 5. ChatGPT architecture/report review prompt

```text
This is the repository discovery/implementation/review report for <task>.
Evaluate it as product architect and final quality judge.

Check whether it matches the approved business decisions, reuses the existing
system, protects data/finance/authorization, has a bounded next phase, includes
credible acceptance criteria, and reports tests honestly. Point out unsupported
claims, missing product decisions, unsafe scope, and the exact corrections
needed before Mohamed approves implementation or commit.
```
