#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  scripts/restore_db.sh — restore a backup made by scripts/backup_db.sh
#
#  Usage:
#      ./scripts/restore_db.sh <dump_file|latest> <target_db_name>
#
#  Examples:
#      ./scripts/restore_db.sh latest resort_os_restore_test   # safe: new/scratch DB
#      ./scripts/restore_db.sh backups/resort_os_20260703_030000.dump resort_os
#          ↑ restoring OVER the real database — requires typing the target
#            db name back as confirmation (disaster-recovery path).
#
#  Connection info comes from backend/.env's DATABASE_URL, same as
#  backup_db.sh — <target_db_name> overrides just the database name, host/
#  port/user/password stay the same (both dev and prod publish Postgres to
#  127.0.0.1 on the host).
#
#  Offsite fallback (wagdy.md T-04): if `latest` is requested and the local
#  backups/ dir has nothing (real disaster recovery — server rebuilt from
#  scratch, backups/ itself is gone with it), and BACKUP_REMOTE_ENABLED +
#  BACKUP_RCLONE_REMOTE are set in backend/.env (same vars backup_db.sh
#  uses), automatically pull the newest dump from the offsite remote first.
#  A local backup always wins over the remote if both exist — no network
#  round-trip needed for the common case.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/backend/.env"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"

DUMP_ARG="${1:-}"
TARGET_DB="${2:-}"

if [[ -z "$DUMP_ARG" || -z "$TARGET_DB" ]]; then
  echo "Usage: $0 <dump_file|latest> <target_db_name>" >&2
  exit 1
fi

[[ -f "$ENV_FILE" ]] || { echo "✗ $ENV_FILE not found" >&2; exit 1; }

DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
read -r DB_USER DB_PASS DB_HOST DB_PORT SOURCE_DB_NAME < <(python3 -c "
from urllib.parse import urlparse
u = urlparse('$DATABASE_URL'.replace('postgresql+psycopg://', 'postgresql://'))
print(u.username, u.password, u.hostname, u.port or 5432, u.path.lstrip('/'))
")

BACKUP_RCLONE_REMOTE="${BACKUP_RCLONE_REMOTE:-$(grep -E '^BACKUP_RCLONE_REMOTE=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)}"
BACKUP_RCLONE_CONFIG="${BACKUP_RCLONE_CONFIG:-$(grep -E '^BACKUP_RCLONE_CONFIG=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)}"

# ── Resolve dump file ───────────────────────────────────────────────────────
if [[ "$DUMP_ARG" == "latest" ]]; then
  DUMP_FILE="$(find "$BACKUP_DIR" -name "${SOURCE_DB_NAME}_*.dump" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"
  if [[ -z "$DUMP_FILE" && -n "$BACKUP_RCLONE_REMOTE" ]] && command -v rclone &>/dev/null; then
    echo "→ No local backups in $BACKUP_DIR — trying offsite remote $BACKUP_RCLONE_REMOTE"
    RCLONE_ARGS=()
    [[ -n "$BACKUP_RCLONE_CONFIG" ]] && RCLONE_ARGS=(--config "$BACKUP_RCLONE_CONFIG")
    LATEST_REMOTE="$(rclone "${RCLONE_ARGS[@]}" lsf "$BACKUP_RCLONE_REMOTE" --files-only 2>/dev/null \
      | grep -E "^${SOURCE_DB_NAME}_.*\.dump\$" | sort -r | head -1 || true)"
    if [[ -n "$LATEST_REMOTE" ]]; then
      mkdir -p "$BACKUP_DIR"
      echo "→ Downloading $LATEST_REMOTE from offsite remote..."
      rclone "${RCLONE_ARGS[@]}" copyto "$BACKUP_RCLONE_REMOTE/$LATEST_REMOTE" "$BACKUP_DIR/$LATEST_REMOTE"
      DUMP_FILE="$BACKUP_DIR/$LATEST_REMOTE"
    fi
  fi
  [[ -n "$DUMP_FILE" ]] || { echo "✗ No backups found in $BACKUP_DIR (or offsite remote)" >&2; exit 1; }
else
  DUMP_FILE="$DUMP_ARG"
fi
[[ -f "$DUMP_FILE" ]] || { echo "✗ Dump file not found: $DUMP_FILE" >&2; exit 1; }

echo "→ Dump file:  $DUMP_FILE"
echo "→ Target DB:  $TARGET_DB @ $DB_HOST:$DB_PORT"

# ── Safety guard: restoring over an existing DB with real tables requires
#    explicit confirmation — the whole point is to prevent a fat-fingered
#    restore from silently wiping live data. Restoring into a DB that
#    doesn't exist yet (scratch/test/disaster-recovery-onto-fresh-Postgres)
#    skips the prompt since there's nothing to lose. ───────────────────────
DB_EXISTS="$(PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='$TARGET_DB'")"

if [[ "$DB_EXISTS" == "1" ]]; then
  TABLE_COUNT="$(PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
  if [[ "$TABLE_COUNT" -gt 0 ]]; then
    echo ""
    echo "⚠️  '$TARGET_DB' already exists and has $TABLE_COUNT table(s)."
    echo "⚠️  Restoring will DROP and recreate every object in it — irreversible."
    echo ""
    read -r -p "Type the target database name to confirm ('$TARGET_DB'): " CONFIRM
    if [[ "$CONFIRM" != "$TARGET_DB" ]]; then
      echo "✗ Confirmation did not match — aborted, nothing was touched." >&2
      exit 1
    fi
  fi
else
  echo "→ '$TARGET_DB' does not exist yet — creating it."
  PGPASSWORD="$DB_PASS" createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$TARGET_DB"
fi

echo "→ Restoring..."
PGPASSWORD="$DB_PASS" pg_restore \
  -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB" \
  --clean --if-exists --no-owner --no-privileges \
  "$DUMP_FILE"

echo "✓ Restore complete into '$TARGET_DB'"
