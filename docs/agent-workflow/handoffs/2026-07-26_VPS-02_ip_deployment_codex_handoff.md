# VPS-02 — IP-only production deployment handoff

**Date:** 2026-07-26  
**Operator:** Codex  
**State:** application online on the public IPv4; operational bootstrap/data deferred  
**Supersedes:** the deployment/DNS/TLS state in `2026-07-26_VPS-01_codex_handoff.md`  
**Commit / push:** none

## User decision controlling this release

Mohamed explicitly decided:

1. do not depend on `elkheimabeachresort.com`;
2. use the VPS IPv4 only;
3. publish the current safe state now and defer the remaining product work.

The old domain and the Hostinger provider hostname are not runtime origins,
certificate identifiers, CORS origins, public links, or acceptance
dependencies for this release.

## Live endpoints

- Staff application: `https://191.218.161.133`
- Marketing/guest website: `https://191.218.161.133:8443`
- Backend health through the staff proxy:
  `https://191.218.161.133/health`

External GET checks returned `200` for the staff root/login/health and the
marketing root, rooms, booking, contact, and privacy routes. Port `80`
redirects permanently to HTTPS. Port `8081` was removed from the published
Compose ports and UFW and has no host listener.

## Exact source identity

This release intentionally deploys an uncommitted shared worktree based on Git
`27cc217`; it must not be described as that commit alone.

The local and VPS trees were hashed independently after transfer and matched:

- Resort operational tree SHA-256:
  `3ed94cdaffec5e3964a711a33287791b4c059148abcd783bcbb5939fa871e8a5`
- Marketing tree SHA-256:
  `9e9c40d5b47675f3ddb1adb80974aecaa230d18242d164fa1f6be4876a6d3158`

The resort operational digest excludes documentation, environment files,
ignored secrets, virtual environments, build/runtime output, logs, SQLite
files, and backups.
The marketing digest excludes `.git`, `.env*`, `node_modules`, `dist`, and
logs. `backend/.env.prod` was transferred separately over SSH, installed as
`resortos:resortos` mode `0600`, and never included in a Docker build layer.

## Build and database evidence

- Backend full regression:
  `2151 passed, 38 skipped, 0 failed` in `360.71s`.
- Marketing:
  - public-truth validation: pass;
  - TypeScript check: pass;
  - production build: pass (`2039` modules);
  - `npm audit --audit-level=high`: `0 vulnerabilities`.
- Production environment validator: pass locally and on the VPS.
- Production Compose config with the IP TLS overlay: pass.
- All five application images built on the VPS.
- PostgreSQL started empty and `alembic upgrade head` completed through the
  complete historical chain.
- Confirmed database revision: `c4d8e2f6a901 (head)`.
- Production database counts after migration:
  - users: `0`;
  - branches: `0`;
  - legacy demo users: `0`.
- `app.seed` was not run.

## Runtime state

Compose project: `resort-os-prod`.

Running services:

- PostgreSQL 16;
- Redis 7;
- FastAPI backend;
- Celery worker;
- Celery beat;
- staff SPA;
- marketing SPA;
- Nginx `1.30.4-alpine` edge.

Every defined container healthcheck passed. All eight containers had
`RestartCount=0`. A focused ten-minute log scan found no traceback, critical
error, unhandled exception, or runtime error.

## TLS and network

- A trusted Let's Encrypt certificate was issued directly for
  `191.218.161.133`.
- Certificate SAN is critical `IP Address:191.218.161.133`.
- Validity: `2026-07-26` through `2026-08-02` (expected short-lived IP
  certificate).
- Renewal was reconfigured from standalone to webroot
  `/var/www/certbot` while Nginx remains online.
- `certbot renew --cert-name 191.218.161.133 --dry-run
  --no-random-sleep-on-renew`: pass.
- The repository deploy hook validates Nginx then reloads the exact production
  container without parsing Compose secrets.
- `resort-os-certbot-renew.timer` is enabled and active; its service completed
  successfully.
- UFW permits only rate-limited SSH, `80`, `443`, and `8443`.
- The provider firewall still contains its historical `8081` allow rule, but
  UFW blocks it and no process listens on it. Remove that redundant provider
  rule during the next Hostinger-control maintenance.
- The older provider-hostname certificate remains on disk but is unused.

## Security containment in the deployed UI

- Chat remains build-time disabled (`CHATBOT_ENABLED=false`).
- No production Host-to-branch mapping exists yet, so public branch-bound
  contact/chat endpoints fail closed.
- Unverified marketing claims remain fail-closed.
- The built marketing files contain no
  `elkheimabeachresort.com` string.
- Marketing consent/tracking defaults to denied.
- Staff and marketing roots emit CSP, frame denial, MIME-sniffing denial,
  referrer, permissions, cross-origin, and HSTS protections.
- Backend and marketing Docker build contexts exclude `.env*`; production
  secrets are runtime-only.
- The two legacy Digital Hub feedback calls that violated the new consent
  contract were removed from this release. Feedback returns only with a
  dedicated, consent-aware operational contract.

## Backup and recovery evidence

- `resort-os-backup.timer` is enabled and active.
- A real custom-format dump was created:
  `resort_os_20260726_192726.dump` (`529065` bytes).
- A real restore was performed into the disposable database
  `resort_os_restore_probe_20260726`.
- Restored state contained `135` public tables and Alembic revision
  `c4d8e2f6a901`.
- The disposable restore database was dropped by the cleanup trap.
- Off-server encrypted backup remains deferred. The temporary Hostinger
  snapshot is not a substitute for it.

## Intentionally deferred / required next

The web applications are online, but the operational system deliberately has
no invented users, branches, rooms, prices, or bookings.

1. Mohamed creates a named Super Admin interactively so the one-time temporary
   password and enrollment token never appear in an agent transcript:

   ```bash
   ssh -tt resort-os-vps \
     'docker exec -it resort-os-prod-backend-1 python -m app.admin_bootstrap create'
   ```

2. Complete password replacement, TOTP enrollment, recovery-code custody, and
   a verified 2FA login.
3. Initialize the first approved branch interactively using the owner's real
   code/name:

   ```bash
   ssh -tt resort-os-vps \
     'docker exec -it resort-os-prod-backend-1 python -m app.admin_bootstrap init-first-branch'
   ```

4. Bind `191.218.161.133` to that branch in the production Host map, revalidate
   the environment, and restart backend/Celery. Only then do contact intake
   tests become a release gate.
5. Import approved real operational data through dry-run/reconciliation
   tooling; never run `app.seed` in production.
6. Finish active-branch frontend integration, public room/rate contract,
   device/browser UAT, off-server backups, monitoring/alerts, and remaining
   Medium/Low plan items.

There is no DNS or domain cutover step in this release. Any later agent must
treat IP-only operation as the latest user decision unless Mohamed explicitly
changes it.
