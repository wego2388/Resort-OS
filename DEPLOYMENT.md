# Production Operations — El Kheima Beach Resort OS

**Current model:** immutable releases on the IP-only VPS
**Current host:** `191.218.161.133`
**SSH alias:** `resort-os-vps`
**Compose project:** `resort-os-prod`

This is the only live deployment runbook. The previous host/runbook is
archived in
`docs/archive/2026-07-execution/DEPLOYMENT_OLD_HOST_AND_LEGACY_RUNBOOK.md`
and must not be executed.

Current commit, release directory, image IDs, backup paths, and rollback
evidence are recorded in `PROJECT_STATUS.md` and the latest release handoff.
Never substitute values from an old handoff.

## 1. Production layout

```text
/opt/resort-os/                       legacy source snapshot; not a deploy target
/opt/resort-os-releases/<commit>/     immutable application release
/opt/elkheima-marketing-website/      marketing-site build context
/var/backups/resort-os/
  source-releases/                    release archives and rollback manifests
  source-snapshots/                   preserved legacy production source
/etc/letsencrypt/                     IP certificate
/var/www/certbot/                     ACME webroot
```

The active Compose files are:

```text
docker-compose.prod.yml
docker-compose.prod.ip-tls.yml
```

Do not use a domain override while the IP-only decision is active.

## 2. Safety rules

- Connect as `resortos` with the SSH key; use `sudo` only where required.
- Do not enable root/password SSH or weaken UFW/Fail2ban.
- Never print `backend/.env.prod` or Docker container environment values.
- Do not clean, reset, pull, or rebuild inside `/opt/resort-os`.
- Every release needs a reviewed commit, archive SHA-256, DB backup, previous
  image tags, migration compatibility check, and external smoke tests.
- Never run `app.seed` in production.
- Never run `scripts/wait-dns-then-switch.sh` without a new owner decision.
- A compatible application rollback does not justify restoring the database.

## 3. Daily status

```bash
ssh resort-os-vps

docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}' | sort
curl -fsS http://127.0.0.1:8005/health
curl -fsS https://191.218.161.133/health
curl -fsSI https://191.218.161.133:8443/

systemctl --failed
systemctl status resort-os-backup.timer --no-pager
systemctl status resort-os-certbot-renew.timer --no-pager
df -h /
free -h
```

Resolve the currently active release from the running backend instead of
guessing a path:

```bash
RESORT_ACTIVE_RELEASE=$(docker inspect resort-os-prod-backend-1 \
  --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')
test -n "$RESORT_ACTIVE_RELEASE"
printf '%s\n' "$RESORT_ACTIVE_RELEASE"
```

The read-only systemd health gate runs every five minutes:

```bash
systemctl status resort-os-healthcheck.timer --no-pager
systemctl status resort-os-healthcheck.service --no-pager
journalctl -u resort-os-healthcheck.service --since today --no-pager
sudo systemctl start resort-os-healthcheck.service
```

It checks backend/DB/Redis health, both HTTPS applications, all eight
containers, daily-backup freshness, at least 48 hours of certificate validity,
and root-disk usage below 85%. A failed check exits non-zero and is retained in
the systemd journal. External delivery still requires a separately approved
notification channel.

## 4. Compose environment without exposing secrets

Compose needs the database password used inside `DATABASE_URL`. Derive it in
memory from the active release; never echo it:

```bash
cd "$RESORT_ACTIVE_RELEASE"

RESORT_DATABASE_URL=$(sed -n 's/^DATABASE_URL=//p' backend/.env.prod | head -n 1)
RESORT_DB_PASSWORD=$(RESORT_DATABASE_URL="$RESORT_DATABASE_URL" python3 -c '
import os
from urllib.parse import urlparse

url = os.environ["RESORT_DATABASE_URL"].replace(
    "postgresql+psycopg://", "postgresql://", 1
)
password = urlparse(url).password
if not password:
    raise SystemExit("DATABASE_URL has no password")
print(password)
')
export DB_PASSWORD="$RESORT_DB_PASSWORD"

RESORT_COMPOSE=(
  docker compose
  --env-file backend/.env.prod
  -f docker-compose.prod.yml
  -f docker-compose.prod.ip-tls.yml
)

"${RESORT_COMPOSE[@]}" config --quiet
```

Unset the derived shell values when the operation ends:

```bash
unset DB_PASSWORD RESORT_DB_PASSWORD RESORT_DATABASE_URL
```

## 5. Controlled immutable release

### A. Local release gate

From the reviewed branch:

```bash
bash scripts/agent-check.sh
git diff --check
git status --short --branch
git rev-parse HEAD

cd backend
.venv/bin/pytest tests/ -q
.venv/bin/alembic heads

cd ../frontend
pnpm --filter el-kheima test:frontend
pnpm run type-check:all
pnpm run build:all
```

The release commit must be pushed to its explicit branch. Do not move `main`
as an incidental deployment step.

### B. Release artifact

Create a Git archive from the exact commit, calculate its SHA-256, copy it to
`/var/backups/resort-os/source-releases/`, and verify the same checksum on the
VPS. Extract it only into a new `/opt/resort-os-releases/<commit>` directory.
Never overwrite an existing release directory.

Copy the current production `.env.prod` to the new release with mode `0600`
without displaying it. Make `MARKETING_SITE_CONTEXT` point to the existing
absolute marketing checkout if the copied relative value does not resolve
from the new directory. Run:

```bash
python3 scripts/validate_prod_env.py --env backend/.env.prod
```

### C. Rollback point

Before any build retags an image name, tag the currently running images under:

```text
resort-os-rollback/backend:pre-<commit>
resort-os-rollback/celery-worker:pre-<commit>
resort-os-rollback/celery-beat:pre-<commit>
resort-os-rollback/el-kheima:pre-<commit>
```

Record their full image IDs under
`/var/backups/resort-os/source-releases/<commit>-rollback-images.txt`.

Create a fresh database dump:

```bash
ENV_FILE=backend/.env.prod COMPOSE_PROJECT_NAME=resort-os-prod \
  bash scripts/backup_db.sh
```

Do not continue unless the dump exists and `pg_restore --list` can read it.

### D. Build and preflight

With `RESORT_COMPOSE` configured for the new release:

```bash
"${RESORT_COMPOSE[@]}" build --parallel \
  backend celery_worker celery_beat el_kheima

"${RESORT_COMPOSE[@]}" run --rm --no-deps backend \
  python -c 'from app.main import app; print(app.title)'

"${RESORT_COMPOSE[@]}" run --rm --no-deps backend alembic heads
"${RESORT_COMPOSE[@]}" run --rm backend alembic upgrade head
```

Stop if import, Compose validation, backup, or migration fails. A build alone
does not change the running containers.

### E. Controlled replacement

Replace in dependency order and wait for health after each stage:

```bash
"${RESORT_COMPOSE[@]}" up -d --no-deps backend
"${RESORT_COMPOSE[@]}" up -d --no-deps celery_worker celery_beat
"${RESORT_COMPOSE[@]}" up -d --no-deps el_kheima
"${RESORT_COMPOSE[@]}" up -d --no-deps --force-recreate nginx
```

Do not recreate PostgreSQL, Redis, or the marketing site when they are outside
the release scope.

## 6. Post-release acceptance

Verify all of the following:

```bash
docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}' | sort
curl -fsS https://191.218.161.133/health
curl -fsSI https://191.218.161.133/
curl -fsSI https://191.218.161.133:8443/

docker exec resort-os-prod-backend-1 alembic current
docker exec resort-os-prod-db_postgres-1 \
  psql -U postgres -d resort_os -Atc \
  "SELECT 'users='||count(*) FROM users UNION ALL SELECT 'branches='||count(*) FROM branches;"
```

Also verify:

- full image IDs and `RestartCount=0`;
- updated containers use the new release `working_dir` label;
- staff and marketing titles render from outside the VPS;
- TLS SAN matches `191.218.161.133`;
- DB/Redis ports remain loopback-only;
- backend/Celery/Nginx logs contain no new traceback, critical, fatal, or
  emergency event;
- no temporary restore database remains.

Document the evidence in a release handoff before declaring REL complete.

## 7. Application rollback

Rollback only when a release acceptance condition fails or a verified
regression requires it.

1. Read the exact rollback manifest for the active release.
2. Retag the preserved rollback images to the normal Compose image names.
3. Recreate backend, Celery, El Kheima, and Nginx in the same controlled order.
4. Re-run every health, TLS, DB, listener, and log check.

For `ac7764f`, the preserved tags are recorded in
`docs/agent-workflow/handoffs/2026-07-29_REL-02_codex_handoff.md`.

The current encryption migration widens columns and has a no-op downgrade.
Do not shrink those columns during application rollback. Restore the database
only after proving actual data corruption and selecting a dated dump with the
owner.

## 8. Backup and disaster recovery

- The production timer creates daily local PostgreSQL dumps.
- An encrypted AES-256 copy exists off the VPS and has passed a full isolated
  restore drill.
- Provider snapshots remain recommended but do not replace the tested
  database copy.
- Never write a decrypted production dump to an unprotected local path.
- Test restores in a uniquely named temporary database, compare expected
  schema/version/counts, then remove it and independently confirm removal.

See `docs/agent-workflow/handoffs/2026-07-29_DR-01_codex_handoff.md`.

## 9. TLS

The public certificate is an IP certificate for `191.218.161.133`.

```bash
sudo certbot certificates
sudo certbot renew --dry-run
systemctl status resort-os-certbot-renew.timer --no-pager

echo | openssl s_client \
  -connect 127.0.0.1:443 \
  -servername 191.218.161.133 2>/dev/null |
  openssl x509 -noout -issuer -dates -ext subjectAltName
```

Do not introduce a domain to solve certificate renewal; the tested IP renewal
path is the current design.

## 10. Super-admin recovery

Prefer a second active super-admin and recovery codes. If server-side recovery
is required, resolve the active release and use the maintained wrapper scripts:

```bash
RESORT_ACTIVE_RELEASE=$(docker inspect resort-os-prod-backend-1 \
  --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')
cd "$RESORT_ACTIVE_RELEASE"

bash scripts/vps-recover-admin.sh operator@example.com
bash scripts/vps-create-admin.sh operator@example.com "Operator Full Name"
```

Do not place a password, recovery code, enrollment token, or TOTP secret in a
handoff, shell history, command line, or chat transcript.
