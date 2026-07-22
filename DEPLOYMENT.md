# Deployment Guide — El Kheima Beach (resort-os)

Step-by-step instructions for standing this up on a fresh Ubuntu VPS.
`resort-os` is fully self-contained — one repo, one build context, no
external shared-package dependency. `git clone` and go.

## 1. Install Docker + Docker Compose (Ubuntu 22.04/24.04)

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Run docker without sudo (log out/in afterwards for this to take effect)
sudo usermod -aG docker "$USER"

docker --version
docker compose version
```

## 2. Clone `resort-os`

```bash
sudo mkdir -p /opt/wegosharm && sudo chown "$USER":"$USER" /opt/wegosharm
cd /opt/wegosharm
git clone <your-resort-os-remote-url> resort-os
cd resort-os
```

> **⚠️ If you also run local dev on this same machine/checkout**:
> `docker-compose.prod.yml` pins `name: resort-os-prod` at its top specifically
> so its volumes/network never collide with `docker-compose.yml`'s (which
> default to the `resort-os` project name — the checkout's directory name).
> Without that pin, `docker compose -f docker-compose.prod.yml down -v` would
> tear down and silently wipe the *dev* Postgres/Redis volumes too, since
> Compose scopes volumes by project name and both files would otherwise
> resolve to the same one. On a real, dedicated VPS this scenario doesn't
> arise (there's no dev stack to collide with), but the pin costs nothing and
> stays as a permanent guard rail.

## 3. Create `backend/.env.prod` with real production secrets

```bash
cp backend/.env.example backend/.env.prod
```

Generate real values for the secrets below and edit them into `backend/.env.prod`
(never commit this file — it's gitignored):

```bash
# SECRET_KEY — 64 random hex chars
openssl rand -hex 32

# FIELD_ENCRYPTION_KEY — Fernet key (encrypts PII columns: national_id, etc.)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# SURVEY_TOKEN_SECRET — 32 random hex chars
openssl rand -hex 16
```

At minimum, also set for production:

```env
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://postgres:<DB_PASSWORD>@db_postgres:5432/resort_os
REDIS_URL=redis://redis_cache:6379/0
CELERY_BROKER_URL=redis://redis_cache:6379/1
CELERY_RESULT_BACKEND=redis://redis_cache:6379/2
CORS_ORIGINS=https://app.yourdomain.com,https://yourdomain.com
RESORT_NAME=El Kheima Beach

# Mandatory outside development/test/testing. Startup fails closed if either
# this flag or a valid FIELD_ENCRYPTION_KEY is missing.
LOGIN_2FA_ENFORCED=true
TWO_FACTOR_ENROLLMENT_TOKEN_TTL_MINUTES=30
# Anonymous customer registration is off unless a deployment explicitly needs it.
PUBLIC_REGISTRATION_ENABLED=false

# Optional but recommended for production — see §9 and §10
SENTRY_DSN=https://xxxx@oXXXXXX.ingest.sentry.io/XXXXXXX
```

Note the hostnames: inside `docker-compose.prod.yml`, Postgres and Redis are
reached by their **service names** (`db_postgres`, `redis_cache`), not
`localhost` — that only worked in local dev because those ports were
published to the host. They're still *also* published to `127.0.0.1` on the
host in prod (see docker-compose.prod.yml) — that's deliberate, it's what
lets `scripts/backup_db.sh` run directly on the host (§10) without going
through `docker compose exec`.

Also set a real `DB_PASSWORD` (used by both `docker-compose.prod.yml`'s
`db_postgres` service and your `DATABASE_URL` above) — either export it in
your shell before `docker compose up`, or put `DB_PASSWORD=...` in a
`.env` file at the repo root (Compose reads that automatically).

## 4. Build and initialize the stack

```bash
docker compose -f docker-compose.prod.yml up -d db_postgres redis_cache
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
docker compose -f docker-compose.prod.yml run --rm backend python -m app.admin_bootstrap create
```

The bootstrap command is interactive. It asks for a named operator and email,
then prints a random temporary password plus a separate enrollment token once.
Keep them separately and deliver them out-of-band. Neither secret can be
provided as a command-line argument or stored in deployment configuration.

For operational resilience, create a second named super-admin owned by a
different person and complete both onboarding journeys before go-live:

```bash
docker compose -f docker-compose.prod.yml run --rm backend python -m app.admin_bootstrap create
```

Then start the complete stack:

```bash
docker compose -f docker-compose.prod.yml up -d
```

`app.seed` is deliberately unavailable here, so migrations and the privileged
bootstrap do **not** create a resort branch, outlets, taxes, payment methods,
or other operational reference data. Configure and verify that reference data
through approved administrative/data-migration procedures before serving real
traffic. A dedicated production reference-data initializer remains an open
deployment gate; do not copy the demo seed as a shortcut.

This builds, in order as dependencies require:
- `db_postgres`, `redis_cache` — same images as local dev
- `backend` — via `backend/Dockerfile` (self-contained, `backend/` is the
  entire build context)
- `celery_worker`, `celery_beat` — same image as `backend`, different command
- `el_kheima`, `public_site` — via `frontend/Dockerfile`, one build per
  app (`--build-arg APP_NAME=...`), each producing a small nginx image
  serving that app's static build
- `nginx` — the public edge proxy (see §7)

Check everything came up healthy:

```bash
docker compose -f docker-compose.prod.yml ps
```

## 5. Existing-account recovery and first login

Never run `app.seed` in production. It creates a complete synthetic business
dataset and known development identities, and now fails explicitly outside
`development`, `test`, or `testing`.

To recover an existing account (including a legacy seeded super-admin or
accountant) without changing its role:

```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.admin_bootstrap recover
```

Recovery preserves the existing role, rotates the password, disables the old
factor, clears refresh/recovery sessions, and issues a new short-lived
enrollment token. It cannot promote an ordinary account.

The user-visible onboarding sequence is:

1. Sign in with the temporary password and enrollment token.
2. Replace the temporary password (all prior sessions are revoked).
3. Sign in again with the new password and the same unexpired token.
4. Bind an authenticator, verify the six-digit code, and save all eight
   one-time recovery codes separately from the phone.
5. Sign in again with a fresh TOTP code. A bootstrap session never receives a
   seven-day refresh cookie.

If the enrollment token expires, run `recover` again. Do not disable
`LOGIN_2FA_ENFORCED` as a recovery shortcut.

After the named super-admin has completed password replacement and 2FA, use
**Settings → Staff Accounts** to create ordinary staff identities. Creation
requires a fresh password + 2FA step-up and returns a random temporary
password plus a separate enrollment token once; neither secret is stored in
browser storage. Optionally select an existing HR employee record during
creation so attendance, leave, payroll, and profile self-service resolve to
the same login. The web control plane cannot create a `super_admin`; create a
second named super-admin only with the local bootstrap command above.

After at least one named super-admin has completed password replacement and
2FA and successfully signed in, disable the documented seed identities:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml \
  exec backend python -m app.admin_bootstrap disable-legacy-demo
```

The command refuses to run before that replacement account is fully enrolled,
requires an exact interactive confirmation, revokes demo sessions, and writes
one audit event.

## 6. DNS

This deployment routes by **subdomain**, not path, because neither of the two
frontend apps have a configured base path (see the routing-decision comment
at the top of `docker-compose.prod.yml`). Point DNS A records at your VPS's IP:

| Hostname | App |
|---|---|
| `app.yourdomain.com` | `el-kheima` (staff) |
| `yourdomain.com` + `www.yourdomain.com` | `public` (guest booking site + QR ordering/beach-checkin/survey) |

## 7. TLS with certbot

`docker-compose.prod.yml`'s `nginx` service mounts two volumes that certbot
needs: `certbot_www` (for the HTTP-01 challenge, already wired into
`deploy/nginx/edge.conf`'s `/.well-known/acme-challenge/` location) and
`certbot_certs` (mounted read-only at `/etc/letsencrypt`, where
`deploy/nginx/edge.conf` expects each domain's cert). Simplest path — install
certbot on the **host** (not in a container) and let it write directly into
the same path the `certbot_certs` named volume backs:

```bash
sudo apt-get install -y certbot

# Find where the certbot_certs volume actually lives on disk:
docker volume inspect resort-os-prod_certbot_certs --format '{{ .Mountpoint }}'
# then either:
#   (a) symlink /etc/letsencrypt on the host to that mountpoint, or
#   (b) stop nginx, run certbot standalone, copy certs into that mountpoint, restart nginx

# Easiest in practice — stop the edge nginx briefly, use certbot's standalone
# mode (it binds port 80 itself), then restart:
docker compose -f docker-compose.prod.yml stop nginx
sudo certbot certonly --standalone \
  -d app.yourdomain.com -d yourdomain.com -d www.yourdomain.com
# certbot writes to /etc/letsencrypt on the host by default — bind-mount that
# instead of a named volume if you go this route (edit docker-compose.prod.yml:
# change `certbot_certs:/etc/letsencrypt:ro` to `/etc/letsencrypt:/etc/letsencrypt:ro`)
docker compose -f docker-compose.prod.yml start nginx
```

Before any of this, edit **`deploy/nginx/edge.conf`** and replace every
`yourdomain.com` placeholder with your real domain (two server blocks +
the shared HTTP→HTTPS redirect block).

Set up renewal (`certbot renew` twice daily via cron/systemd timer is
standard) and have it reload the `nginx` container after renewal:

```bash
# /etc/cron.d/certbot-renew
0 3,15 * * * root certbot renew --quiet --deploy-hook \
  "docker compose -f /opt/wegosharm/resort-os/docker-compose.prod.yml exec -T nginx nginx -s reload"
```

### 7A. Publicly trusted TLS when only the VPS IP is available

Let's Encrypt supports short-lived IP certificates. Certbot 5.4 or newer is
required for the webroot/IP flow. These certificates last about six days, so
the included twice-daily renewal timer is mandatory rather than optional.

Start the HTTP edge first so the ACME challenge path is reachable:

```bash
sudo install -d -m 0755 /var/www/certbot /etc/letsencrypt
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-only.yml up -d nginx

sudo snap install core
sudo snap refresh core
sudo snap install --classic certbot
/snap/bin/certbot --version   # must be 5.4+

sudo /snap/bin/certbot certonly \
  --webroot --webroot-path /var/www/certbot \
  --preferred-profile shortlived \
  --ip-address 187.124.170.249 \
  --cert-name 187.124.170.249 \
  --email theagaty@gmail.com --agree-tos --non-interactive
```

Install renewal and switch the edge to TLS:

```bash
sudo install -m 0755 deploy/certbot/reload-resort-os-nginx.sh \
  /etc/letsencrypt/renewal-hooks/deploy/reload-resort-os-nginx.sh
sudo install -m 0644 deploy/systemd/resort-os-certbot-renew.service \
  deploy/systemd/resort-os-certbot-renew.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now resort-os-certbot-renew.timer
sudo ufw allow 8443/tcp

docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml up -d nginx
curl -fsS https://187.124.170.249/health
curl -fsSI https://187.124.170.249:8443/
sudo /snap/bin/certbot renew --dry-run
```

The staff app is `https://187.124.170.249/`; the guest/public app is
`https://187.124.170.249:8443/`. Set `PUBLIC_SITE_URL` to the latter in
`backend/.env.prod`. Port 8081 remains only as an HTTP redirect to 8443.

## 8. Health check verification

```bash
curl -s https://app.yourdomain.com/health
# → {"status": "ok", "checks": {"database": {...}, "redis": {...}}, ...}

docker compose -f docker-compose.prod.yml ps            # all healthy?
docker compose -f docker-compose.prod.yml logs backend --tail 100
```

If `/health` doesn't respond: check `docker compose -f docker-compose.prod.yml
logs backend`, confirm `alembic upgrade head` succeeded (step 5), and confirm
`db_postgres`/`redis_cache` show `healthy` in `docker compose ps`.

## 9. Error tracking (Sentry)

Set `SENTRY_DSN` in `backend/.env.prod` (get one free at sentry.io — a new
project of type "FastAPI"/"Python") and restart the backend:

```bash
docker compose -f docker-compose.prod.yml restart backend celery_worker celery_beat
docker compose -f docker-compose.prod.yml logs backend | grep Sentry
# → [Sentry] initialized for 'Resort OS' env='production'
```

Without `SENTRY_DSN` set, the app runs fine — errors just aren't reported
anywhere except the container logs (`docker compose logs backend`), which is
fine for local dev but means real production errors go unnoticed until a
user reports them. Setting this is cheap and worth doing before go-live.

## 10. Database backups — set this up before real guest data exists

`scripts/backup_db.sh` and `scripts/restore_db.sh` (repo root) run directly
against Postgres on `127.0.0.1:5436` (published to the host by both
docker-compose.yml and docker-compose.prod.yml — see the note in §3) using
the same `DATABASE_URL` from the environment file the app itself reads, so there's
nothing extra to configure.

**Manual test run** (do this once after first deploy to confirm it actually
works on this server, not just in theory):

```bash
ENV_FILE=backend/.env.prod ./scripts/backup_db.sh
# → backups/resort_os_<timestamp>.dump

# Prove it restores cleanly, into a throwaway DB (never overwrites anything real):
./scripts/restore_db.sh latest resort_os_restore_test
docker compose -f docker-compose.prod.yml exec db_postgres \
  psql -U postgres -d resort_os_restore_test -c "SELECT count(*) FROM users;"
# compare against the real DB's user count — should match exactly

docker compose -f docker-compose.prod.yml exec db_postgres \
  psql -U postgres -c "DROP DATABASE resort_os_restore_test;"   # clean up
```

**Real disaster recovery** (restoring over the actual `resort_os` database,
e.g. after a server rebuild) uses the same script — it detects the target
already has tables and requires you to type the database name back as
confirmation before it touches anything:

```bash
./scripts/restore_db.sh backups/resort_os_20260703_030000.dump resort_os
```

**Schedule it** — a systemd timer is provided (daily at 03:00, deliberately
clear of the app's own scheduled jobs in `app/celery_app.py`):

```bash
sudo cp deploy/systemd/resort-os-backup.service deploy/systemd/resort-os-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now resort-os-backup.timer
systemctl list-timers resort-os-backup.timer   # confirm it's scheduled
```

Edit `WorkingDirectory=`/`User=` in `resort-os-backup.service` first if your
checkout path or run user differs from `/opt/wegosharm/resort-os` / `resortos`.

Retention defaults to 14 days (`BACKUP_RETENTION_DAYS` env var to change).
Backups land in `backups/` at the repo root — gitignored.

**Offsite sync** (wagdy.md T-04) — for real disaster recovery (the server
itself dying, not just the database), `backup_db.sh` can also push every
fresh dump to S3/Backblaze B2/any `rclone`-supported remote in the same run.
Set in `backend/.env.prod` (unset by default — the local-only flow above works
exactly the same either way):

```bash
# requires: rclone installed + `rclone config` already run once for the remote
BACKUP_REMOTE_ENABLED=true
BACKUP_RCLONE_REMOTE=b2:my-bucket/resort-os-backups   # or s3:bucket/path, etc.
```

`restore_db.sh latest` automatically falls back to pulling the newest dump
from this same remote if `backups/` is empty (e.g. after a full server
rebuild) — no separate disaster-recovery procedure to remember.

## Updating / redeploying

```bash
cd /opt/wegosharm/resort-os
DEPLOY_BRANCH=release/vps-ready-2026-07-22 bash scripts/deploy.sh
```

The deployment script refuses a dirty worktree, takes a point-in-time backup,
fast-forwards only the selected branch, builds, applies Alembic migrations
before replacing services, selects IP TLS automatically when its certificate
exists, and fails if the backend health check does not recover.
