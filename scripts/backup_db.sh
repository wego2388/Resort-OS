#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  scripts/backup_db.sh — real PostgreSQL backup, no cron infrastructure needed
#  besides calling this script on a schedule (see DEPLOYMENT.md).
#
#  Reads connection info from backend/.env's DATABASE_URL (same source of
#  truth the app itself uses) — no separate DB_HOST/DB_PASSWORD vars to keep
#  in sync. Works identically for local dev and prod: both publish Postgres
#  to 127.0.0.1:5436 on the host (see docker-compose.yml / .prod.yml), so
#  this script always connects to the host port, never into the container.
#
#  Usage:
#      ./scripts/backup_db.sh                  # backup + apply retention
#      BACKUP_RETENTION_DAYS=30 ./scripts/backup_db.sh
#
#  Output: backups/resort_os_<UTC timestamp>.dump  (pg_dump custom format,
#  compressed, restorable with pg_restore — see scripts/restore_db.sh)
#
#  Offsite sync (wagdy.md T-04, optional — the local backup/restore/
#  systemd-timer flow above is completely unchanged if this isn't set):
#  set these in backend/.env (same file DATABASE_URL is read from) to also
#  push every fresh dump to S3/Backblaze B2/any rclone-supported remote —
#  "backups only exist on the same server they're protecting against" is a
#  real disaster-recovery gap otherwise (disk failure / VPS lost = backups
#  lost too).
#      BACKUP_REMOTE_ENABLED=true
#      BACKUP_RCLONE_REMOTE=b2:my-bucket/resort-os-backups   # or s3:bucket/path, etc.
#      BACKUP_RCLONE_CONFIG=/opt/wegosharm/.config/rclone/rclone.conf   # optional, defaults to rclone's own default config location
#  Requires `rclone` installed + the remote already configured
#  (`rclone config` — the part before the colon above, e.g. `b2`/`s3`, is
#  the configured remote's name).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/backend/.env}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

[[ -f "$ENV_FILE" ]] || { echo "✗ $ENV_FILE not found" >&2; exit 1; }

# ── Offsite sync config (env wins if already exported, else read from backend/.env) ──
# `|| true` on each grep is required: these vars are optional (unlike
# DATABASE_URL above) so the pattern often won't match, and grep's exit 1
# on no-match would otherwise abort the whole script here (set -o pipefail
# makes a no-match failure propagate out of the `grep | head | cut` pipeline
# even though head/cut themselves "succeed" on empty input).
BACKUP_REMOTE_ENABLED="${BACKUP_REMOTE_ENABLED:-$(grep -E '^BACKUP_REMOTE_ENABLED=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)}"
BACKUP_RCLONE_REMOTE="${BACKUP_RCLONE_REMOTE:-$(grep -E '^BACKUP_RCLONE_REMOTE=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)}"
BACKUP_RCLONE_CONFIG="${BACKUP_RCLONE_CONFIG:-$(grep -E '^BACKUP_RCLONE_CONFIG=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)}"

# ── Parse DATABASE_URL (postgresql+psycopg://user:pass@host:port/dbname) ──────
DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
[[ -n "$DATABASE_URL" ]] || { echo "✗ DATABASE_URL not set in $ENV_FILE" >&2; exit 1; }

read -r DB_USER DB_PASS DB_HOST DB_PORT DB_NAME < <(RESORT_DATABASE_URL="$DATABASE_URL" python3 -c "
import os
from urllib.parse import urlparse
u = urlparse(os.environ['RESORT_DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://'))
print(u.username, u.password, u.hostname, u.port or 5432, u.path.lstrip('/'))
")

mkdir -p "$BACKUP_DIR"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
DUMP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.dump"

echo "→ Backing up '$DB_NAME' @ $DB_HOST:$DB_PORT → $DUMP_FILE"
# Use docker exec if pg_dump is not available on the host (production servers
# typically don't have the postgres client installed). Falls back to direct
# pg_dump if docker is unavailable or the compose stack isn't running.
if ! command -v pg_dump &>/dev/null; then
  # Detect compose project name: resort-os-prod in production, resort-os in dev
  COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-resort-os-prod}"
  DB_CONTAINER="${COMPOSE_PROJECT}-db_postgres-1"
  if docker inspect "$DB_CONTAINER" &>/dev/null; then
    echo "  (pg_dump not on host — running via docker exec $DB_CONTAINER)"
    docker exec -e PGPASSWORD="$DB_PASS" "$DB_CONTAINER" \
      pg_dump -h localhost -U "$DB_USER" -d "$DB_NAME" \
      -Fc --no-owner --no-privileges \
      > "$DUMP_FILE"
  else
    echo "✗ pg_dump not found on host and docker container '$DB_CONTAINER' not running" >&2
    exit 1
  fi
else
  # Production DATABASE_URL uses the Compose service hostname internally.
  # The host reaches the deliberately loopback-only published port instead.
  if [[ "$DB_HOST" == "db_postgres" ]]; then
    DB_HOST="127.0.0.1"
    DB_PORT="5436"
  fi
  PGPASSWORD="$DB_PASS" pg_dump \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -Fc --no-owner --no-privileges \
    -f "$DUMP_FILE"
fi

SIZE="$(du -h "$DUMP_FILE" | cut -f1)"
echo "✓ Backup complete: $DUMP_FILE ($SIZE)"

# ── Offsite sync (optional — see header) ────────────────────────────────────
# Runs after the local dump is confirmed on disk, so a sync failure never
# costs the local backup itself. Exits non-zero on sync failure (loud,
# visible in `systemctl status`/journalctl) rather than swallowing it —
# unlike a purely local failure, an offsite sync failure is easy to miss
# for weeks since the local backup still "looks" successful every day.
if [[ "$BACKUP_REMOTE_ENABLED" == "true" ]]; then
  if [[ -z "$BACKUP_RCLONE_REMOTE" ]]; then
    echo "✗ BACKUP_REMOTE_ENABLED=true but BACKUP_RCLONE_REMOTE is not set in $ENV_FILE" >&2
    exit 1
  fi
  if ! command -v rclone &>/dev/null; then
    echo "✗ BACKUP_REMOTE_ENABLED=true but rclone is not installed on this host" >&2
    exit 1
  fi

  RCLONE_ARGS=()
  [[ -n "$BACKUP_RCLONE_CONFIG" ]] && RCLONE_ARGS=(--config "$BACKUP_RCLONE_CONFIG")

  echo "→ Syncing to offsite remote: $BACKUP_RCLONE_REMOTE"
  if rclone "${RCLONE_ARGS[@]}" copyto "$DUMP_FILE" "$BACKUP_RCLONE_REMOTE/$(basename "$DUMP_FILE")"; then
    echo "✓ Offsite sync complete"
  else
    echo "✗ Offsite sync failed — local backup is still safe at $DUMP_FILE, but it is NOT off this server yet" >&2
    exit 1
  fi
fi

# ── Retention: delete dumps older than RETENTION_DAYS ──────────────────────
DELETED=0
while IFS= read -r -d '' old_file; do
  rm -f "$old_file"
  DELETED=$((DELETED + 1))
done < <(find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -mtime "+${RETENTION_DAYS}" -print0)

if [[ "$DELETED" -gt 0 ]]; then
  echo "✓ Retention: deleted $DELETED backup(s) older than ${RETENTION_DAYS} days"
fi

REMAINING="$(find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" | wc -l)"
echo "→ $REMAINING backup(s) retained in $BACKUP_DIR"
