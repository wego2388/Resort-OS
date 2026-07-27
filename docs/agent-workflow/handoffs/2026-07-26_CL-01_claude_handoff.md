# Handoff CL-01 — Claude

- **Implementer:** Claude
- **Base SHA:** `resort-os` @ `27cc217` (branch `main`, 9 commits ahead of `origin/main`) · `elkheima-marketing-website` @ `74c66f4` (branch `main`, in sync with `origin/main`)
- **Target:** uncommitted diff in both repositories — no commit/push performed
- **Worktree:** shared main working directory in both repos (no dedicated CL-01 worktree was created). While this packet was in progress, Codex was concurrently editing unrelated files in the same `resort-os` directory (`frontend/apps/el-kheima/**`, `docker-compose.prod.yml`, `.github/workflows/ci.yml`, and the shared docs under `docs/agent-workflow/`). None of those files were touched by this packet; see "Concurrent activity" below.
- **Status:** ready for independent review (Codex, packet CX-01); no commit/push performed

## Outcome

The public chatbot on the marketing site (`useChatbot.ts` / previously also `HubConcierge.vue`) called `/chat` and `/concierge/*` with zero matching backend in `resort-os`. This packet:

1. Built a new `chat` module in `resort-os` (models/schemas/crud/services/router), ported from a working implementation in a predecessor project (`elkheima-beach-resort`, uses the same Gemini API) but with `build_system_prompt()` rewritten from scratch to read `resort-os`'s real data (dining menu/prices, beach entry prices, live room availability) instead of the old project's catalog, which doesn't exist here.
2. Fixed the marketing site's chatbot to actually call it (`/api/v1/chat/...` instead of unprefixed `/chat/...`), removed a duplicate floating chat widget (`HubConcierge.vue`) that was stacking on top of the site-wide one on the Hub page, and fixed an unrelated `.env` variable-name bug that silently broke local dev API calls.
3. Went through the Gate 3 security/cost checklist in `docs/audits/EL_KHEIMA_FINAL_EXECUTION_PLAN_AR.md` item by item and closed the real gaps found (see "Gate 3 checklist" below) — this was not a one-pass build; several real bugs were caught by live testing and by tests written against the actual behavior, not assumptions.

The chatbot is live-tested end-to-end against the real Gemini API (not mocked) at every stage, including after every hardening change, to confirm the happy path still works.

## Files changed

### `resort-os`

New:
- `backend/app/modules/chat/` (models.py, schemas.py, crud.py, services.py, api/router.py, `__init__.py` files)
- `backend/alembic/versions/dc6bfb5b79e8_chat_module.py`
- `backend/tests/test_api/test_chat.py` (42 tests)

Modified:
- `backend/app/main.py` — registered `"chat"` in `_MODULE_KEYS`
- `backend/app/core/config.py` — added `GEMINI_API_KEY: Optional[str]`, `GEMINI_MODEL: str`
- `backend/app/core/rate_limit.py` — added 3 route entries for chat endpoints (see "Rate limits" below); added an explanatory comment on `_client_ip` (name unchanged — see "Reverted change" below)
- `backend/.env.example` — documented `GEMINI_API_KEY`/`GEMINI_MODEL`
- `backend/alembic/env.py` — added `import app.modules.chat.models`
- `backend/.env`, `backend/.env.prod` — added `GEMINI_API_KEY` (real value, gitignored, not part of any diff reviewers see)
- `CLAUDE.md`, `PROJECT_STATUS.md` — documented the new module and this hardening round

### `elkheima-marketing-website`

Modified:
- `src/composables/booking/useChatbot.ts` — fixed 4 endpoint paths to `/api/v1/chat/...`; added `session_id` to the main `/chat` call (enables real conversation/message persistence); removed the dead, never-populated `user_name` field
- `src/apps/public/DigitalHub.vue` — removed `<HubConcierge />` usage and its import (duplicate chat widget)
- `src/components/chatbot/ChatbotMessage.vue` — fixed a real XSS vector (see "Security" below)
- `src/api/client.ts` — fixed the `baseURL` fallback (port 8000 → 8005, dropped incorrect `/api` suffix)
- `.env` — fixed a variable-name bug (`VITE_API_BASE_URL` → `VITE_API_URL`, the name `client.ts` actually reads)

Deleted:
- `src/components/hub/HubConcierge.vue` (confirmed zero other importers before deletion; called the dead `/concierge/*` contract)

## API contract

### `POST /api/v1/chat` — main chat turn

No authentication (public, guest-facing). Rate limits: 20 req/60s per IP (route middleware) **and** 300 req/day per IP (in-endpoint, cost cap — see "Rate limits").

Request:
```jsonc
{
  "message": "string, 1-500 chars, required",
  "history": [{"role": "user"|"model", "content": "string, max 500"}],  // max 20 items, default []
  "language": "ar"|"en"|"ru"|"it",  // default "ar"
  "session_id": "string, 8-64 chars, optional",  // ties this turn to a persisted conversation
  "context": {
    "page": "string, max 200, optional",
    "last_topic": "string, max 100, optional",
    "location_type": "string, max 30, optional",   // Gate 8 guest-session location (table/room/umbrella/pergola)
    "location_number": "string, max 30, optional"
    // deliberately no guest identity fields (name/phone/email) — see Security
  }
}
```

Response: `{"reply": "string"}`

Errors:
| Status | Cause |
|---|---|
| 400 | empty/whitespace-only message |
| 422 | Pydantic validation (oversized fields, bad language/role) |
| 429 | per-minute or per-day rate limit exceeded |
| 502 | Gemini returned non-200 or a malformed response |
| 503 | `GEMINI_API_KEY` not configured, or circuit breaker open |
| 504 | Gemini request timed out (15s total, 5s connect) |

### `GET /api/v1/chat/welcome?language=ar`

No auth. Returns `{"message": "..."}` — a branch-aware greeting (real branch name), no AI call.

### `POST /api/v1/chat/conversations/start`

No auth. Body: `{"session_id": str (8-64), "page": str?, "utm_source": str?, "language": "ar"|"en"|"ru"|"it"}`. Idempotent (existing session_id → no-op, `{"success": true}`).

### `POST /api/v1/chat/conversations/{session_id}/end`

No auth. Body: `{"rating": int 1-5, optional}`. Unknown session_id → still `200 {"success": true}` (no information leak about which sessions exist).

## Migration

`dc6bfb5b79e8_chat_module.py`, down_revision `f1a9c3d7e825` (single head, confirmed). Creates `chat_conversations` (branch-scoped, unique `session_id`, `user_rating` CHECK 1-5) and `chat_messages` (FK to conversation, `role`/`message`). Hand-written (not `--autogenerate`), matching this repo's established convention for this reason (autogenerate noise on this schema — see `CLAUDE.md` §13). Verified: `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` — clean round-trip on the real Postgres dev database.

## Rate limits and cost protection

Three independent layers:

1. **Per-minute, per-IP** (`rate_limit.py` middleware, exact-path match): `POST /api/v1/chat` → 20/60s (tighter than the 30/60s used for free reads elsewhere, because this is a real paid AI call per message). `GET /chat/welcome` and `POST /chat/conversations/start` → 30/60s (no AI cost).
2. **Per-day, per-IP** (`chat/services.py::check_daily_cap`, called inside the `chat` endpoint): 300/day. Catches slow-drip abuse that never trips the per-minute limit (e.g., one request every 2 minutes for 24h = 720 real AI calls).
3. **Circuit breaker** (`chat/services.py`): after 5 provider failures (timeout/non-200/malformed response) within 60 seconds, the circuit opens for 30 seconds — every request in that window is rejected immediately with `503`, without attempting a call to Gemini at all. Protects against wasting timeout cycles (and money) hammering a provider that's already down. **Not** tripped by `GEMINI_API_KEY` missing (that's a static config problem, not a transient outage).

Both the daily cap and the circuit breaker reuse the existing `rate_limit()` primitive from `app.core.kernel.cache` (a real sliding-window counter, works against Redis or the in-memory fallback) rather than building parallel counting logic.

## Prompt injection, PII, and untrusted-output handling (Gate 3 checklist)

- **User input is untrusted**: `sanitize_message()` rejects known prompt-injection phrases (`ignore previous`, `system:`, `act as`, Arabic equivalents, etc.) and truncates to 500 chars, before the message ever reaches the prompt.
- **No guest PII sent to the model**: `ChatContext` originally declared `guest_phone`/`user_name` (carried over from the predecessor project's contract) but neither was ever read by any service code, and the frontend's only caller always sent `null` for `user_name` and never sent `guest_phone` at all. Both fields were **removed** from the schema and the frontend payload — a test (`test_no_guest_pii_fields_in_context_schema`) asserts the schema only ever has `page`/`last_topic`/`location_type`/`location_number`, so a future silent re-addition of a guest-identity field fails CI instead of shipping quietly.
- **No secrets in the prompt**: `build_system_prompt()` only reads `Branch`/`dining`/`beach`/`pms` data. Tested explicitly (`test_secrets_never_appear_in_prompt`): `SECRET_KEY`, `GEMINI_API_KEY`, and `DATABASE_URL`/`postgresql` never appear in the generated prompt.
- **Model output is untrusted — real XSS fixed, not just theoretical**: `ChatbotMessage.vue` rendered the AI reply via `v-html="renderMarkdown(message.text)"`. The only defense was a regex, `text.replace(/<[^>]*>/g, '')`, run before injecting its own `<strong>/<em>/<code>/<br>` tags — a pattern-matching HTML stripper is not a trusted sanitizer (Gate 3 explicitly calls this out: "no `v-html` without a trusted sanitizer"). Fixed by escaping via the browser's own encoder (`document.createElement('div').textContent = text; div.innerHTML`) before applying the markdown transforms, guaranteeing any `<`, `>`, `&` in the model's output becomes inert text — zero new dependency. No links are rendered by this markdown subset (bold/italic/code/newline only), so the link-scheme allowlist requirement in Gate 3 doesn't currently apply; flagging this so it's not forgotten if link rendering is ever added.
- **Logs**: no user message or AI reply content is logged anywhere; the only chat-related log line is a truncated (200 char) Gemini *error response* on failure, which never includes the user's message.
- **Retention/encryption — explicitly deferred, not decided unilaterally**: `chat_messages.message` is a free-text column, not `EncryptedString`. Guest-typed messages could incidentally contain PII (a phone number, a name) even though the product never asks for it. `CLAUDE.md`'s `EncryptedString` policy currently applies to `employees`/`bookings`/`timeshare_contracts`/`crm_customers`/`guest_profiles`, not conversation logs, and the execution plan itself lists "retention/privacy decision and the guest-facing terms" as an explicit **owner decision**, not something an implementing agent should decide (`EL_KHEIMA_FINAL_EXECUTION_PLAN_AR.md` §8, point 7). Left as-is with this note rather than guessing at a retention window or unilaterally adding encryption.

## Reverted change: `_client_ip`

Attempted to export `rate_limit.py`'s `_client_ip()` (drop the underscore) so `chat`'s daily-cap check could reuse the same trusted-proxy IP derivation instead of duplicating it. Discovered while running tests that `_client_ip` is also used by `app/core/me_router.py`, `app/core/kernel/auth/router.py`, and has a dedicated security test file (`tests/test_api/test_auth_security_http.py`, 7 assertions) — all auth code, explicitly Codex's territory per the protocol, not CL-01's. Reverted the rename; `chat/api/router.py` imports `_client_ip` directly (same pattern `kernel/auth/router.py` already uses) instead of restructuring a shared auth-adjacent file's public surface.

## Commands run and exact results

```text
cd backend && source .venv/bin/activate

pytest tests/test_api/test_chat.py -v --no-header
→ 42 passed, 1 warning (pytest-asyncio deprecation, pre-existing/unrelated)

pytest tests/ -v --no-header
→ 2126 passed, 34 skipped, 6 warnings, 342.25s
   (34 skipped = pre-existing Postgres-only migration tests, same as baseline)

alembic heads
→ dc6bfb5b79e8 (head)   [single head confirmed]

alembic downgrade -1 && alembic upgrade head
→ clean round-trip, no errors

Live Gemini API call (not mocked), before and after every hardening change:
POST /api/v1/chat {"message": "كام سعر دخول الشاطئ؟"} → 200, real reply with
real beach prices (200/100/150/50 EGP) and, in a follow-up call with location
context, correctly referenced "طاولة رقم 7" / real live room-availability
counts and dining prices pulled from the dev database — confirms the whole
dynamic-prompt pipeline actually works against real data, not just that the
code compiles.
```

```text
cd /home/wego/projects/elkheima-marketing-website

npm run build
→ built in ~9.5s, no errors (re-run after every change, including the XSS fix)
```

No automated frontend test runner is configured for `elkheima-marketing-website` (confirmed — no `package.json` test script, no CI step). Per `AGENTS.md` §7 ("there is no configured frontend lint or automated frontend test command... do not report those checks as passed"), this handoff does **not** claim frontend unit/e2e tests passed — only that `npm run build` (the one real, existing command) is clean. Setting up a frontend test framework would be new tooling/dependency work, out of CL-01's scope, and should be raised as its own decision if wanted.

## Bugs found and fixed during this work (real, not hypothetical — each caught by an actual failing test or a live API call, not inferred)

1. **Gemini rejects a `contents` array ending on a "model" turn.** First version of `get_ai_response()` ended that way when `history` was empty; live call returned 400 `INVALID_ARGUMENT`. Fixed: one fixed priming turn (prompt + canned greeting), then real history if any, then the current message always as the final `user` turn.
2. **`maxOutputTokens=500` (matching the predecessor project) truncated replies mid-sentence.** `gemini-flash-latest` spends a large, variable share of the token budget on invisible "thinking" tokens before the visible reply; `thinkingConfig` to disable it returned 400 (unsupported on this model). Raised to 2048; confirmed via live call with the full production system prompt that replies now complete normally (`finishReason: STOP`).
3. **Circuit breaker off-by-one.** `rate_limit(key, max_requests=N)` returns `True` while the counter is `<= N`, i.e. it *permits* N failures before rejecting — so `max_requests=THRESHOLD` actually tripped after `THRESHOLD + 1` failures, not `THRESHOLD`. Caught by a failing test (`test_circuit_breaker_trips_after_repeated_failures`) before it shipped. Fixed to `max_requests=THRESHOLD - 1`.
4. **Test isolation: `_FakeAsyncClient.post` overwritten without restore.** Three tests directly reassigned the fake HTTP client's `post` method (`fake_gemini.post = _capture`) without reverting it, leaking the override into unrelated later tests in the same file and breaking them non-deterministically depending on test order. Fixed with `monkeypatch.setattr` (auto-reverts) everywhere.
5. **Cache pollution across tests.** `build_system_prompt()`'s cache, and later the circuit-breaker/daily-cap counters, are stored in a process-lifetime cache (Redis or in-memory) that the `db` fixture's per-test rollback does **not** clear. A failure recorded in one test could trip the circuit breaker for an unrelated test that ran afterward. Fixed with one file-level `autouse` fixture clearing all `chat_*`-prefixed cache keys before every test.
6. **Local dev `.env` variable-name mismatch (marketing site, unrelated to the backend but discovered while testing this feature).** `.env` declared `VITE_API_BASE_URL`; `client.ts` reads `VITE_API_URL`. Since the two never matched, every local `npm run dev` session silently fell back to a wrong default (`localhost:8000`, no `/v1`), meaning every `/api/v1/...` call in local dev was double-prefixed and broken — production was unaffected (`VITE_API_URL=""` is set correctly via the Docker build arg). Fixed the variable name/value and the `client.ts` fallback default.

## Concurrent activity noted, not touched

While this packet was in progress, uncommitted changes appeared in the same `resort-os` working directory from Codex's parallel work (CX-02A/CX-03): `frontend/apps/el-kheima/**` (multiple files), `docker-compose.prod.yml`, `frontend/Dockerfile`, `.github/workflows/ci.yml`, `frontend/packages/core/**`, `frontend/pnpm-lock.yaml`, and new files under `frontend/apps/el-kheima/src/__tests__/`, `src/config/`, `src/security/`. **None of these were read, edited, or relied upon by CL-01.** `docs/agent-workflow/EL_KHEIMA_EXECUTION_BOARD.md` was also being edited concurrently by Codex; each edit here re-read the file immediately before writing to avoid clobbering Codex's own section updates.

## Known limitations / deferred (owner or Codex decision, not silently skipped)

1. **`GEMINI_API_KEY` is a shared, temporary key** copied from `elkheima-beach-resort`'s production `.env` — Mohamed's explicit, informed choice on 2026-07-26 to unblock this work now. Both projects currently draw from the same Google billing/quota. A dedicated `resort-os` key is a 2-minute follow-up whenever wanted (`https://aistudio.google.com/apikey`), no code change required beyond swapping the `.env`/`.env.prod` value.
2. **No admin UI for the chatbot's knowledge base or settings.** The predecessor project had one (admin-editable Q&A, settings CRUD); this packet deliberately did not build one — scope was "make the chatbot actually work against real data," not replicate every admin-tooling feature of the old system. `build_system_prompt()` already pulls live dining/beach/pms data, which covers most of what a manual knowledge base would have provided.
3. **`chat_messages.message` retention/encryption** — see "Retention/encryption" above; explicitly an owner decision per the execution plan, not decided here.
4. **CL-02 (marketing site's broader public/staff separation — API client, Service Worker, consent, contact UI)** is explicitly out of scope for CL-01 per the protocol and was not started.

## Reviewer (Codex, CX-01) should focus on

1. Whether the rate-limit/circuit-breaker/daily-cap layering is sufficient, or whether Codex's own security review standard expects something stricter (e.g., session-based limiting in addition to IP-based — IP-based only was the pragmatic choice here given no auth system exists on the public site).
2. Whether `_client_ip` should eventually be promoted to a proper shared/public utility (not reverted permanently — just deferred past CL-01 to avoid touching auth code and its dedicated test file mid-packet).
3. The `ChatContext` schema reduction (`guest_phone`/`user_name` removed) — confirm this matches the intended "no guest data to third-party AI" policy and isn't perceived as removing a wanted future feature without discussion.
4. The XSS fix in `ChatbotMessage.vue` — confirm the escape-then-format approach is an acceptable permanent pattern, or whether Gate 3's "Markdown AST with an allowlist" preference should be revisited with a real library later (deliberately not done here to avoid an unjustified new dependency for a 4-transform feature set).
5. Whether `check_daily_cap`'s 300/day ceiling and the circuit breaker's 5-failures/60s/30s-cooldown constants are reasonable defaults, or should be `Settings`-configurable (currently hardcoded module constants — kept simple since there was no existing per-environment tuning requirement to satisfy).
6. `backend/app/core/rate_limit.py` and `backend/app/core/config.py` are shared files now released back to Codex ownership per the protocol — the diff on each is small and additive (3 new route entries, 2 new settings fields) and should be quick to verify does not conflict with any other in-flight shared-file work.
