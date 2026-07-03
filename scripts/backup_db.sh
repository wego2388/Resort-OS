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
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/backend/.env"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

[[ -f "$ENV_FILE" ]] || { echo "✗ $ENV_FILE not found" >&2; exit 1; }

# ── Parse DATABASE_URL (postgresql+psycopg://user:pass@host:port/dbname) ──────
DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
[[ -n "$DATABASE_URL" ]] || { echo "✗ DATABASE_URL not set in $ENV_FILE" >&2; exit 1; }

read -r DB_USER DB_PASS DB_HOST DB_PORT DB_NAME < <(python3 -c "
import sys
from urllib.parse import urlparse
u = urlparse('$DATABASE_URL'.replace('postgresql+psycopg://', 'postgresql://'))
print(u.username, u.password, u.hostname, u.port or 5432, u.path.lstrip('/'))
")

mkdir -p "$BACKUP_DIR"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
DUMP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.dump"

echo "→ Backing up '$DB_NAME' @ $DB_HOST:$DB_PORT → $DUMP_FILE"
PGPASSWORD="$DB_PASS" pg_dump \
  -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
  -Fc --no-owner --no-privileges \
  -f "$DUMP_FILE"

SIZE="$(du -h "$DUMP_FILE" | cut -f1)"
echo "✓ Backup complete: $DUMP_FILE ($SIZE)"

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
