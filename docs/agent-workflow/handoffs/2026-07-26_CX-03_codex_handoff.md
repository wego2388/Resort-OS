# Handoff CX-03 — Codex

- **Implementer:** Codex
- **Base SHA:** `27cc217`
- **Target:** uncommitted diff in `/home/wego/projects/resort-os`
- **Branch/worktree:** `main` in the shared worktree
- **Status:** ready for independent review; no commit/push performed

## Outcome

CX-03 closes the immediate QR/PWA/operator-isolation failures in the staff app:

1. Production QR builds require one explicit HTTPS guest origin.
2. Staff Service Worker no longer caches authenticated API responses.
3. Legacy API caches are removed before auth restoration and at every identity transition.
4. Offline operational writes are preserved but scoped to their creating employee.
5. Unknown frontend roles/requirements fail closed; `timeshare_agent` matches the Backend.
6. Shift Dashboard reconnects its WebSocket after opening/changing a shift.
7. The existing i18n and dark-theme contrast gate failures are fixed.
8. PostCSS was upgraded to a patched release and the production dependency audit is clean.

## Files changed

### QR and production wiring

- `.github/workflows/ci.yml`
- `docker-compose.prod.yml` — build arg only
- `frontend/Dockerfile`
- `frontend/apps/el-kheima/.env.production.example`
- `frontend/apps/el-kheima/src/config/publicSite.ts`
- `frontend/apps/el-kheima/src/views/admin/QRGeneratorView.vue`
- `frontend/apps/el-kheima/src/vite-env.d.ts`
- `frontend/apps/el-kheima/vite.config.ts`
- `frontend/apps/el-kheima/src/__tests__/config/publicSite.spec.ts`

### PWA/auth/offline identity isolation

- `frontend/apps/el-kheima/src/main.ts`
- `frontend/apps/el-kheima/src/security/staffClientState.ts`
- `frontend/apps/el-kheima/src/__tests__/security/staffClientState.spec.ts`
- `frontend/packages/core/src/api/client.ts`
- `frontend/packages/core/src/stores/auth.ts`
- `frontend/packages/core/src/composables/useOfflineQueue.ts`
- `frontend/apps/el-kheima/src/__tests__/security/authRoleGuard.spec.ts`
- `frontend/apps/el-kheima/src/__tests__/pos/offlineQueueIdentity.spec.ts`

### Quality/lifecycle

- `frontend/apps/el-kheima/src/views/ops/BookingsView.vue`
- `frontend/apps/el-kheima/src/views/pos/ShiftDashboardView.vue`
- `frontend/apps/el-kheima/package.json`
- `frontend/pnpm-lock.yaml`

## Contracts and behavior

### Public QR URL

- Build-time variable: `VITE_PUBLIC_SITE_URL`.
- Production: required, valid absolute HTTPS URL, with no credentials/query/fragment.
- Development only: same hostname with public dev port `5174`.
- Docker receives it from required Compose interpolation `PUBLIC_SITE_URL`.
- CI uses reserved `.invalid` origin only to verify the build contract.

### Staff PWA

- Workbox precaches static assets/app shell only.
- `runtimeCaching` contains no API routes.
- Upgrade cleanup deletes only known legacy API cache names; current static precache is retained.
- Cleanup runs before auth refresh and is awaited on login, PIN switch, logout, and refresh failure.

### Offline queue identity

- New records store `ownerUserId`.
- Counts, sync, and sync logs expose only records owned by the active employee.
- A PIN switch during a sync stops before the next request.
- Legacy records lacking an owner are quarantined and never attributed to the next employee.
- No offline record is deleted merely because an employee logs out.

### Role guard

- `timeshare_agent = 25`, matching `backend/app/core/deps.py`.
- Unknown current roles and unknown minimum-role requirements return `false`.
- Unknown `roleLevel` is `-1`, not guest level.

### Shift WebSocket

- Connection scope is branch + shift.
- Opening a shift from an initially empty screen now establishes the WebSocket.
- Closing/changing a shift disconnects the old socket.
- Reconnect timers and stale socket handlers are cancelled on scope change/unmount.

## Validation evidence

```text
pnpm --filter el-kheima type-check
PASS

pnpm --filter el-kheima validate:i18n
PASS — ar/en parity 5919 keys, 56 strict screens

pnpm --filter el-kheima test:unit
PASS — 13 files, 86 tests
Note: jsdom still prints its pre-existing window.scrollTo warning; tests pass.

VITE_PUBLIC_SITE_URL=https://public.example.invalid pnpm --filter el-kheima build
PASS — 1067 modules, PWA generated

pnpm --filter el-kheima build  # without VITE_PUBLIC_SITE_URL
EXPECTED FAIL — required production value

generated dist/sw.js forbidden API-cache scan
PASS — no /api/v1 or legacy cache names

pnpm audit --prod
PASS — No known vulnerabilities found

PUBLIC_SITE_URL=https://public.example.invalid \
  docker compose -f docker-compose.prod.yml config --quiet
PASS

Docker image build
BuildKit path blocked by a local Docker Hub TLS certificate mismatch.
No TLS bypass was used.
Legacy builder with locally trusted base images: PASS.
Image: resort-os-el-kheima:cx03

Local nginx image smoke test on 127.0.0.1:18081
PASS — HTTP index served; test container stopped and removed

git diff --check
PASS
```

## Security/data/branch/UX notes

- Physical QR codes fail closed instead of silently embedding a staff/dev origin.
- API data cannot be replayed from Workbox after logout/operator change.
- Offline sales remain recoverable and cannot silently move to another employee's audit identity.
- Branch-scoping of offline records remains dependent on CX-02's real active-branch contract.
- The large initial JavaScript chunk warning remains a [Low] performance item.
- Manifest `dir/lang` is still Arabic-first; localized install metadata remains [Low].

## Known limitations / follow-up

1. Ownerless legacy offline records need an explicit manager recovery/report tool if any real terminal already contains them.
2. CX-02 must replace the frontend `branch_id ?? 1` contract and extend queue filtering to the server-validated active branch.
3. The production domain remains unconfirmed, so no real QR has been generated.
4. BuildKit failed because the local Docker path returned a certificate for an unrelated AWS hostname. This environment issue must be fixed; do not disable TLS verification.
5. Bundle is still about 697 kB minified in the main chunk.

## Reviewer focus

Claude should review:

1. Offline queue behavior across offline → PIN switch → online.
2. The async auth cleanup path during refresh failure and logout.
3. Production URL validation and Docker/Compose propagation.
4. Whether removing all API runtime caches matches the accepted staff offline policy.
5. Shift socket lifecycle across no shift → open → close → reopen.
6. Whether quarantined legacy IDB records require UI before release.

