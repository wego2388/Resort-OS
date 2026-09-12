#!/usr/bin/env bash
# Create a restorable archive of the private, already-encrypted document vault.
# Normally called by backup_db.sh so the database dump and document archive
# share one UTC timestamp. It can also be run independently for a restore drill.
#
# Optional overrides:
#   DOCUMENT_STORAGE_SOURCE=/absolute/path
#   DOCUMENT_BACKUP_PREFIX=resort_os
#   BACKUP_TIMESTAMP=20260912_120000
#   BACKUP_DIR=/var/backups/resort-os
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/backend/.env}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
BACKUP_PREFIX="${DOCUMENT_BACKUP_PREFIX:-resort_os}"
TIMESTAMP="${BACKUP_TIMESTAMP:-$(date -u +%Y%m%d_%H%M%S)}"
ARCHIVE="$BACKUP_DIR/${BACKUP_PREFIX}_documents_${TIMESTAMP}.tar.gz"
BACKEND_CONTAINER="${DOCUMENT_BACKEND_CONTAINER:-resort-os-prod-backend-1}"

mkdir -p "$BACKUP_DIR"

archive_local_directory() {
  local source_dir="$1"
  tar -C "$source_dir" -czf "$ARCHIVE" .
}

if [[ -n "${DOCUMENT_STORAGE_SOURCE:-}" ]]; then
  [[ -d "$DOCUMENT_STORAGE_SOURCE" ]] || {
    echo "✗ Document storage source is not a directory: $DOCUMENT_STORAGE_SOURCE" >&2
    exit 1
  }
  echo "→ Backing up encrypted document vault from $DOCUMENT_STORAGE_SOURCE"
  archive_local_directory "$DOCUMENT_STORAGE_SOURCE"
elif command -v docker >/dev/null 2>&1 && docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1; then
  if docker exec "$BACKEND_CONTAINER" test -d /app/private-documents; then
    echo "→ Backing up encrypted document vault from $BACKEND_CONTAINER"
    docker exec "$BACKEND_CONTAINER" tar -C /app/private-documents -czf - . > "$ARCHIVE"
  else
    # First deployment only: the previous release predates the private volume,
    # so the correct paired backup is an intentionally empty archive.
    empty_dir="$(mktemp -d)"
    trap 'rm -rf -- "$empty_dir"' EXIT
    echo "→ Private document vault does not exist yet; creating an empty baseline archive"
    archive_local_directory "$empty_dir"
  fi
else
  configured_root="$(grep -E '^DOCUMENT_STORAGE_ROOT=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  configured_root="${configured_root:-private-documents}"
  if [[ "$configured_root" = /* ]]; then
    local_source="$configured_root"
  else
    local_source="$ROOT/backend/$configured_root"
  fi
  if [[ -d "$local_source" ]]; then
    echo "→ Backing up encrypted document vault from $local_source"
    archive_local_directory "$local_source"
  else
    empty_dir="$(mktemp -d)"
    trap 'rm -rf -- "$empty_dir"' EXIT
    echo "→ Private document vault is empty; creating an empty baseline archive"
    archive_local_directory "$empty_dir"
  fi
fi

[[ -s "$ARCHIVE" ]] || { echo "✗ Document backup archive is empty or missing" >&2; exit 1; }
tar -tzf "$ARCHIVE" >/dev/null
(cd "$BACKUP_DIR" && sha256sum "$(basename "$ARCHIVE")" > "$(basename "$ARCHIVE").sha256")
chmod 600 "$ARCHIVE" "$ARCHIVE.sha256"
echo "✓ Document backup complete: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
