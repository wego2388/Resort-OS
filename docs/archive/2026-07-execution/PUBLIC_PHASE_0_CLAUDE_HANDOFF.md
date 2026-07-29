# Public Phase 0 — Claude execution handoff

## Control

- **Status:** approved for evidence collection
- **Product owner:** Mohamed
- **Implementation engineer:** Claude Code
- **Independent reviewer:** Codex
- **Repository:** `/home/wego/projects/resort-os`
- **Legacy reference:** `/home/wego/projects/elkheima-beach-resort/frontend`
- **Current public app:** `/home/wego/projects/resort-os/frontend/apps/public`
- **Branch at approval:** `chore/agent-workflow-foundation`
- **Base commit at approval:** `b26a2e3`
- **Execution mode:** read, run safe local checks, and write Phase 0 evidence only

The worktree already contains uncommitted owner/agent work. Preserve it. Do not
reformat, revert, stage, commit, or modify any file outside the output paths
listed below.

## Product outcome

Freeze a reviewable, human-readable reference of every public page and the
Digital Hub in the legacy application, compare it with the current public app,
and define exactly what is worth keeping, adapting, or removing before any code
migration starts.

The current Resort OS backend is the only future source of truth for prices,
availability, bookings, Dining, guest calls, payments, and operational data.
Legacy backend behavior and sample data are evidence only and must not be
copied into Resort OS.

## Confirmed decisions

1. The product name is **El Kheima**.
2. The public site keeps Arabic, English, Russian, and Italian as independently
   reviewed guest languages. Arabic is RTL; the other three are LTR.
3. The desired QR mode is `view_and_call`; unrestricted guest self-ordering is
   not the default.
4. QR is still experimental. No printed code is currently an operational
   compatibility commitment.
5. The goal is selective visual/content reuse, not importing the legacy
   backend, database, security model, or operational admin application.
6. `frontend/apps/public` stays in the current pnpm/Vite workspace and continues
   using `@resort-os/core` and `@resort-os/ui` where appropriate.
7. Phase 0 may run now because it changes no product behavior. Migration remains
   locked behind approval of this evidence and the safety, Super Admin, i18n,
   and design-system gates in `docs/audits/SMART_EXECUTION_ROADMAP.md`.

## Hard scope boundary

### Allowed

- Read both repositories and the current backend/API implementation.
- Run non-destructive discovery, type-check, build, and local preview commands.
- Capture local screenshots without logging into production or mutating data.
- Create or update files only under:
  `docs/audits/public-phase-0/`.
- Use `/tmp/el-kheima-public-phase-0/` for generated/intermediate evidence.

### Forbidden in Phase 0

- No Vue/CSS/TypeScript/Python implementation changes.
- No copying legacy components, assets, translations, fixtures, or data into
  product directories.
- No backend, API, schema, model, migration, permission, QR, payment, or realtime
  changes.
- No dependency installation or package-lock changes without stopping first.
- No database writes, seed changes, destructive commands, remote deployment, or
  calls to production services.
- No `.env` inspection/output, secret copying, commit, push, staging, stash,
  reset, clean, or history rewrite.
- Do not edit `wagdy.md` in this pass; Codex will review the report first and the
  project owner will merge the accepted summary afterward.

If a safe local run requires missing secrets, external accounts, destructive
state, or a dependency installation, record the blocker and continue with
static evidence where possible. Do not improvise authority.

## Required execution stages

### 0A — Preflight and evidence rules

1. Read `AGENTS.md`, `CLAUDE.md`, `wagdy.md`, the three accepted decisions in
   `docs/decisions/`, `docs/audits/PRODUCTION_READINESS_AUDIT.md`, and
   `docs/audits/SMART_EXECUTION_ROADMAP.md`.
2. Record branch, HEAD, dirty status, tool versions, and whether each app can be
   built or safely previewed. Do not alter the dirty state.
3. Define canonical viewports before screenshots:
   desktop `1440x1024` and mobile `390x844`; add tablet only when the layout has
   a distinct state that materially affects migration.
4. Every evidence item must record source path, route, locale, viewport/state,
   date, and whether it came from a live local render or static inspection.

### 0B — Pilot before exhaustive capture

Use three representative legacy journeys first:

- Home
- Rooms list/details
- Digital Hub / menu

Capture Arabic desktop/mobile and English desktop/mobile when each route can be
rendered safely. Inspect Russian/Italian localization completeness and capture
one representative LTR shell for each; do not duplicate identical screenshots
without information value.

Record the pilot screenshot count and total size. Prefer WebP or optimized PNG
when tooling already exists. If exhaustive capture would create excessive
binary volume, keep full images under `/tmp` and commit only a contact sheet or
selected evidence index after owner review.

### 0C — Complete public route and state inventory

Map every route in the legacy public route group, including locale-prefixed
variants, redirects, detail routes, booking/payment result states, legal pages,
404, and the Digital Hub. Keep staff/admin/ERP routes out of migration scope;
list them only when a public page depends on them.

For each route record:

- route name/pattern and locale behavior;
- source view, layout, important child components and composables;
- static, dynamic, transactional, or guest-service classification;
- required params/query/token and safe representative state;
- loading, empty, success, validation, error, offline, and unavailable states;
- responsive/RTL/LTR behavior and primary user task;
- external integrations and current API calls;
- matching current `apps/public` route/component, if any;
- evidence status: rendered, build-only, static-only, or blocked.

Do the same for all current `frontend/apps/public` routes so missing and
conflicting coverage is explicit.

### 0D — Visual system and asset inventory

Inventory the legacy and current:

- logos, icons, fonts, colors, spacing, radii, shadows, breakpoints, grids;
- headers, footers, navigation, hero sections, cards, forms, tables, modals,
  status/error/loading/empty patterns;
- photos/video/backgrounds and responsive variants;
- public source, license/provenance, dimensions, format, byte size, and usage;
- duplicate/near-duplicate assets by hash or demonstrable identity;
- remote URLs and runtime dependencies that would break offline/slow networks.

Do not assume an attractive component is accessible or reusable. Note contrast,
focus, semantics, keyboard, touch target, reduced-motion, Arabic typography,
outdoor readability, and performance debt separately.

### 0E — Content, localization, and SEO map

For every public page map:

- headings, calls to action, facts, prices, policies, contact information, and
  legal claims to their source;
- Arabic/English/Russian/Italian key coverage, hard-coded strings, fallback
  behavior, mistranslations/placeholders, and URL-locale behavior;
- title, description, canonical, hreflang, Open Graph, structured data, image
  alt text, heading hierarchy, and crawl/index assumptions;
- content that can be preserved verbatim, needs business verification, or must
  be generated from the current backend.

Never treat legacy prices, availability, phone numbers, legal wording, or
marketing claims as authoritative without marking them for owner verification.

### 0F — API and data-contract comparison

Trace each legacy public action from UI to client/service/API. Then inspect the
current Resort OS backend route/schema/service used or intended for the same
capability.

For every contract record:

- user action and public route;
- legacy HTTP method/path/request/response and trust assumptions;
- current HTTP method/path/request/response and authorization/rate-limit rules;
- authoritative current module and owner;
- exact compatibility gap or adapter needed later;
- PII, money, availability, token, idempotency, CSRF/CORS, abuse, and error
  handling risks;
- decision: reuse current contract, add a safe public projection later, adapt
  the UI, or remove the action.

Explicitly audit the legacy Digital Hub/cart/waiter-call behavior against the
accepted `view_and_call` decision and the current Dining public routes. Do not
design or implement the future secure QR domain in this phase.

### 0G — Keep / Adapt / Remove matrix and migration batches

Classify each page, component family, content group, asset group, and public
interaction:

- **Keep:** safe to preserve substantially, with evidence.
- **Adapt:** useful intent/design but must be rebuilt against current contracts,
  design tokens, accessibility, performance, or security rules.
- **Remove:** duplicate, unsafe, misleading, obsolete, admin-only, unsupported,
  or inconsistent with the accepted product.
- **Needs decision:** only when a real product fact cannot be inferred.

Every classification needs rationale, source, target, dependencies, risk, and
an observable acceptance check. Propose small migration batches, beginning with
shell/tokens and non-transactional pages. Do not schedule QR, booking, payment,
or other transactional cutovers before their backend safety dependencies.

### 0H — Self-review and handoff

Review the report for omissions, invented behavior, hidden failed commands,
secrets/PII, accidental legacy-backend adoption, and unsupported claims. Run
`git diff --check`, show status/diff stat, and verify that only the approved
documentation output path changed.

Stop after reporting the result. Do not begin migration batch 1.

## Required deliverables

Create this structure:

```text
docs/audits/public-phase-0/
├── README.md
├── 01_ROUTE_AND_STATE_INVENTORY.md
├── 02_VISUAL_REFERENCE_INDEX.md
├── 03_DESIGN_AND_ASSET_INVENTORY.md
├── 04_CONTENT_I18N_SEO_MAP.md
├── 05_API_AND_DATA_CONTRACT_MAP.md
├── 06_KEEP_ADAPT_REMOVE_MATRIX.md
├── 07_MIGRATION_BATCH_PROPOSAL.md
├── 08_OPEN_QUESTIONS_AND_RISKS.md
└── evidence-manifest.json
```

`README.md` is the plain-language executive index and must tell Mohamed:

- what exists in each project;
- what can save time;
- what must not be copied;
- the highest-risk conflicts;
- the smallest recommended first migration batch;
- exactly what evidence remains blocked or unverified.

`evidence-manifest.json` contains metadata and paths/hashes only. Generated
screenshots should remain under `/tmp/el-kheima-public-phase-0/` during review
unless a small, intentional subset is approved for the repository.

## Acceptance criteria

Phase 0 passes only when:

1. Every canonical legacy public route and every current public route has one
   inventory row and an evidence status.
2. Home, Rooms, and Digital Hub have comparable Arabic/English desktop/mobile
   visual evidence or a documented, reproducible blocker.
3. Four-locale coverage and direction behavior are mapped; missing or weak
   translations are visible, not silently treated as complete.
4. Every important public API/action is traced to a current backend owner or
   clearly marked as absent/unsafe/deferred.
5. Every reusable unit has Keep/Adapt/Remove/Needs decision plus evidence and
   rationale.
6. No legacy backend, database, secret, user data, or operational admin code is
   proposed as a source of truth.
7. The Digital Hub explicitly respects `view_and_call`; no guest action can be
   mistaken for approved self-ordering, payment, or kitchen submission.
8. The proposed batches respect the smart-roadmap gates and are small enough for
   one implementation/review cycle each.
9. Failed/unrun commands and static-only conclusions are reported honestly.
10. The product diff contains documentation under the approved output path only.

## Final Claude report format

1. Executive result and recommendation.
2. Routes/pages found: legacy vs current.
3. Most valuable reusable design/content/assets.
4. Unsafe or obsolete elements rejected.
5. API/data conflicts and the current authoritative owners.
6. Pilot visual evidence and blocked states.
7. Proposed first migration batch and why it is reversible.
8. Files created.
9. Every command run and result.
10. Residual risks and true owner decisions.
11. Explicit statement: no migration, backend, API, DB, dependency, commit, or
    push was performed.
