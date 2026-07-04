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

## 3. Create `backend/.env` with real production secrets

```bash
cp backend/.env.example backend/.env
```

Generate real values for the secrets below and edit them into `backend/.env`
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
CORS_ORIGINS=https://app.yourdomain.com,https://qr.yourdomain.com,https://yourdomain.com
RESORT_NAME=El Kheima Beach

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

## 4. Build and start the stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

This builds, in order as dependencies require:
- `db_postgres`, `redis_cache` — same images as local dev
- `backend` — via `backend/Dockerfile` (self-contained, `backend/` is the
  entire build context)
- `celery_worker`, `celery_beat` — same image as `backend`, different command
- `el_kheima`, `qr`, `public_site` — via `frontend/Dockerfile`, one build per
  app (`--build-arg APP_NAME=...`), each producing a small nginx image
  serving that app's static build
- `nginx` — the public edge proxy (see §7)

Check everything came up healthy:

```bash
docker compose -f docker-compose.prod.yml ps
```

## 5. Run migrations and seed data

Once `backend` is up and healthy:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend python -m app.seed
```

`app.seed` is idempotent — safe to re-run; it only creates the super admin,
default branch, modules, and chart of accounts if they don't already exist.
Immediately change the seeded admin password (`admin@resortos.local` /
`Admin@123456`) after first login — it's a well-known default.

## 6. DNS

This deployment routes by **subdomain**, not path, because none of the three
frontend apps have a configured base path (see the routing-decision comment
at the top of `docker-compose.prod.yml`). Point three DNS A records at your
VPS's IP:

| Hostname | App |
|---|---|
| `app.yourdomain.com` | `el-kheima` (staff) |
| `qr.yourdomain.com` | `qr` (guest QR ordering) |
| `yourdomain.com` + `www.yourdomain.com` | `public` (guest booking site) |

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
  -d app.yourdomain.com -d qr.yourdomain.com -d yourdomain.com -d www.yourdomain.com
# certbot writes to /etc/letsencrypt on the host by default — bind-mount that
# instead of a named volume if you go this route (edit docker-compose.prod.yml:
# change `certbot_certs:/etc/letsencrypt:ro` to `/etc/letsencrypt:/etc/letsencrypt:ro`)
docker compose -f docker-compose.prod.yml start nginx
```

Before any of this, edit **`deploy/nginx/edge.conf`** and replace every
`yourdomain.com` placeholder with your real domain (three server blocks +
the shared HTTP→HTTPS redirect block).

Set up renewal (`certbot renew` twice daily via cron/systemd timer is
standard) and have it reload the `nginx` container after renewal:

```bash
# /etc/cron.d/certbot-renew
0 3,15 * * * root certbot renew --quiet --deploy-hook \
  "docker compose -f /opt/wegosharm/resort-os/docker-compose.prod.yml exec -T nginx nginx -s reload"
```

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

Set `SENTRY_DSN` in `backend/.env` (get one free at sentry.io — a new
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
the same `DATABASE_URL` from `backend/.env` the app itself reads, so there's
nothing extra to configure.

**Manual test run** (do this once after first deploy to confirm it actually
works on this server, not just in theory):

```bash
./scripts/backup_db.sh
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
Backups land in `backups/` at the repo root — gitignored, and **not** copied
off the server by anything in this repo. For real disaster recovery (the
server itself dying, not just the database), also sync `backups/` somewhere
off-box — e.g. a nightly `rclone`/`rsync` to S3/Backblaze — that part is
infrastructure-specific and left to you.

## Updating / redeploying

```bash
cd /opt/wegosharm/resort-os && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

Migrations are deliberately a manual step (not baked into the container's
start command) so a routine restart never silently re-runs them. Consider
running `./scripts/backup_db.sh` manually right before a redeploy that
includes a migration, as a point-in-time safety net beyond the nightly timer.
