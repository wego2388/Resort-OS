# El Kheima Agent Workflow

This directory turns broad product ideas into small, reviewable engineering
changes. It supplements `AGENTS.md` and `CLAUDE.md`; it does not replace them.

## Team responsibilities

| Role | Responsibility | Must not do by default |
|---|---|---|
| Mohamed | Product owner: priorities, business decisions, operational acceptance, commit approval | Delegate irreversible business decisions implicitly |
| ChatGPT | Product/architecture partner: understand prompts, expose trade-offs, turn ideas into task briefs, judge agent reports | Claim repository behavior without inspecting evidence |
| Claude Code | Implementation engineer: inspect broad code areas, implement one approved phase, run checks, prepare a diff | Commit, push, or expand scope before review |
| Codex | Independent reviewer: inspect the same diff for correctness, security, data integrity, UX, and missing tests | Edit during a review-only pass |

## The standard lifecycle

### 1. Establish a safe baseline

From the repository or task worktree:

```bash
git status --short --branch
git branch --show-current
git rev-parse --short HEAD
git worktree list
bash scripts/agent-check.sh
```

If remote synchronization is needed, fetch first and inspect divergence:

```bash
git fetch origin
git log --left-right --graph --oneline HEAD...origin/main
```

Do not assume `origin/main` is newer or that local `main` should be reset. The
local branch may contain reviewed work that has not been pushed yet.

### 2. Convert the idea into a task contract

Use `TASK_BRIEF_TEMPLATE.md`. A task is not ready for implementation until it
has:

- one concrete product outcome;
- confirmed business decisions and explicit assumptions;
- a bounded phase and an out-of-scope list;
- data, financial, authorization, API, and UX invariants;
- observable acceptance criteria;
- an appropriate validation plan.

A large master prompt is treated as a product charter. It should be split into
phases before any code change.

### 3. Discovery pass (read-only)

Claude reads the relevant architecture, code, migrations, frontend callers,
and tests. It reports the current implementation, root causes, reusable parts,
risks, expected files, migration strategy, and tests. No file is changed in
this pass when the task brief requires an approval gate.

### 4. Implement one phase

Claude implements only the approved phase, using focused changes. It runs
targeted checks while working and the full affected-layer checks at the phase
gate. It then shows:

```bash
git status --short --branch
git diff --stat
git diff
git diff --check
```

No commit is created unless Mohamed asks for it.

### 5. Independent review in the same worktree

Open a second terminal at the exact worktree where Claude has the uncommitted
changes, then run Codex in review-only mode. This is essential: a different
worktree cannot see uncommitted files from Claude's worktree.

Codex uses `REVIEW_TEMPLATE.md` and separates:

- regressions introduced by this diff;
- pre-existing defects exposed by the review;
- optional improvements outside the task.

### 6. Evidence-based remediation

Send Codex findings back to Claude. Claude verifies each finding against the
code and classifies it as:

- correct and fixed now;
- correct but intentionally deferred, with reason and risk;
- incorrect, with evidence.

Claude fixes only valid in-scope findings, reruns the relevant checks, and
shows the new diff.

### 7. Owner acceptance and commit

Mohamed reviews the operational behavior and final report. Only after approval:

```bash
git add path/to/reviewed-file another/reviewed-file
git commit -m "type(scope): concise outcome"
```

Pushing remains a separate explicit action.

## Worktree rules

Use one worktree per implementation task. Base it on an explicit reviewed
commit, not on an assumed branch state:

```bash
git worktree add ../resort-os-task \
  -b feature/short-task-name \
  <reviewed-base-commit>
```

Separate worktrees are appropriate for independent tasks with non-overlapping
files. They are not the right mechanism for reviewing another worktree's
uncommitted diff. Never remove an existing worktree until its branch, status,
and ownership are understood.

Git does not copy ignored local environments into a new worktree. A new
worktree may therefore need its own documented backend environment and
`pnpm install`, or an explicitly managed local link to a trusted existing
environment. Run `scripts/agent-check.sh` inside that worktree and do not claim
validation if `.venv` or `node_modules` is absent.

## Phase quality gate

Before moving to a new phase:

1. The phase acceptance criteria are demonstrably met.
2. Tests for changed behavior exist and pass.
3. Backend authorization and audit behavior have been checked.
4. Financial/data invariants and concurrency risks have been checked.
5. Frontend TypeScript/build checks pass when frontend code changed.
6. Migration heads and migration impact are clear when models changed.
7. Codex has reviewed the diff and all Critical/High findings are resolved or
   explicitly blocked by a user decision.
8. `wagdy.md` explains the result and remaining risk in plain Arabic.
9. Mohamed approves the result before commit or the next phase.

## Files in this workflow

- `TASK_BRIEF_TEMPLATE.md`: contract for one bounded task or phase.
- `PROMPT_LIBRARY.md`: copy/paste prompts for discovery, implementation,
  review, and remediation.
- `REVIEW_TEMPLATE.md`: evidence format for an independent review.
- `PUBLIC_PHASE_0_CLAUDE_HANDOFF.md`: approved, read-only evidence contract for
  comparing the legacy and current public sites before any migration.
- `../../wagdy.md`: Mohamed's plain-language project dashboard.
- `../decisions/`: accepted product decisions that future sessions must keep.
