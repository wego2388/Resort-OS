#!/usr/bin/env bash
# Verify and restore a private-document archive made by backup_documents.sh.
# The target defaults to the production Docker volume mountpoint when it can be
# resolved. An empty target is restored without a prompt. A non-empty target is
# preserved beside it and requires typing its exact resolved path first.
#
# Usage:
#   DOCUMENT_STORAGE_TARGET=/tmp/vault-restore ./scripts/restore_documents.sh backup.tar.gz
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE="${1:-}"
VOLUME_NAME="${DOCUMENT_VOLUME_NAME:-resort-os-prod_resort_documents}"

[[ -n "$ARCHIVE" ]] || { echo "Usage: $0 <document-archive.tar.gz>" >&2; exit 1; }
[[ -f "$ARCHIVE" ]] || { echo "✗ Archive not found: $ARCHIVE" >&2; exit 1; }
[[ -f "$ARCHIVE.sha256" ]] || { echo "✗ Checksum not found: $ARCHIVE.sha256" >&2; exit 1; }

echo "→ Verifying checksum and archive paths"
(cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$ARCHIVE").sha256")
DOCUMENT_ARCHIVE="$ARCHIVE" python3 - <<'PY'
import os
import tarfile
from pathlib import PurePosixPath

with tarfile.open(os.environ["DOCUMENT_ARCHIVE"], "r:gz") as archive:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"unsafe archive path: {member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"unsafe archive entry type: {member.name}")
PY

target="${DOCUMENT_STORAGE_TARGET:-}"
if [[ -z "$target" ]] && command -v docker >/dev/null 2>&1; then
  target="$(docker volume inspect "$VOLUME_NAME" --format '{{.Mountpoint}}' 2>/dev/null || true)"
fi
[[ -n "$target" ]] || {
  echo "✗ Set DOCUMENT_STORAGE_TARGET or create Docker volume '$VOLUME_NAME'" >&2
  exit 1
}

mkdir -p "$target"
target="$(realpath "$target")"
if [[ "$target" == "/" || "$target" == "$ROOT" || "$target" == "$ROOT/backend" ]]; then
  echo "✗ Refusing unsafe restore target: $target" >&2
  exit 1
fi

previous=""
target_was_empty="false"
if find "$target" -mindepth 1 -print -quit | grep -q .; then
  echo "⚠️  The target is not empty: $target"
  read -r -p "Type the exact target path to preserve and replace it: " confirmation
  [[ "$confirmation" == "$target" ]] || {
    echo "✗ Confirmation did not match; nothing was changed" >&2
    exit 1
  }
  previous="${target}.pre-restore.$(date -u +%Y%m%d_%H%M%S)"
else
  target_was_empty="true"
fi

staging="$(mktemp -d "${target}.restore.XXXXXX")"
restore_failed() {
  local exit_code=$?
  if [[ -n "$staging" && -d "$staging" ]]; then
    rm -rf -- "$staging"
  fi
  if [[ -n "$previous" && -d "$previous" && ! -e "$target" ]]; then
    mv "$previous" "$target"
  elif [[ "$target_was_empty" == "true" && ! -e "$target" ]]; then
    mkdir -p "$target"
  fi
  exit "$exit_code"
}
trap restore_failed ERR

tar -xzf "$ARCHIVE" -C "$staging" --no-same-owner --no-same-permissions
find "$staging" -type d -exec chmod 700 {} +
find "$staging" -type f -exec chmod 600 {} +

# The staging directory is a sibling of the target, so rename is atomic on the
# same filesystem. Preserve a non-empty previous vault until the operator has
# separately verified the restored application.
if [[ -n "$previous" ]]; then
  mv "$target" "$previous"
else
  rmdir "$target"
fi
mv "$staging" "$target"
staging=""
trap - ERR

echo "✓ Document restore complete: $target"
if [[ -n "$previous" ]]; then
  echo "→ Previous vault preserved at: $previous"
fi
