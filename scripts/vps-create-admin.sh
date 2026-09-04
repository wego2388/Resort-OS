#!/usr/bin/env bash
# vps-create-admin.sh — run this ON THE VPS to bootstrap a named super-admin.
# Exists because the equivalent one-liner (nested quotes + heredoc inside an
# ssh single-quoted string) is too fragile to paste reliably in a terminal —
# any reflow/partial paste leaves bash stuck on a dangling `>` continuation
# prompt. This script takes the email/name as plain arguments instead.
#
# Usage (from the VPS shell, after `ssh resort-os-vps`):
#   bash vps-create-admin.sh <email> "<full name>"
#
# Prints the same output app.admin_bootstrap always prints: a one-time
# temporary password + 2FA enrollment token. Copy them immediately — they
# are shown once.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: bash $0 <email> \"<full name>\"" >&2
  exit 1
fi

EMAIL="$1"
FULL_NAME="$2"

RESORT_RELEASE_DIR="${RESORT_RELEASE_DIR:-$(docker inspect \
  resort-os-prod-backend-1 \
  --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' \
  2>/dev/null || true)}"
if [[ -z "$RESORT_RELEASE_DIR" || ! -d "$RESORT_RELEASE_DIR" ]]; then
  echo "Active Resort OS release directory could not be resolved" >&2
  exit 1
fi
cd "$RESORT_RELEASE_DIR"

DATABASE_URL_VALUE=$(grep -E '^DATABASE_URL=' backend/.env.prod | head -1 | cut -d= -f2-)
DB_PASSWORD=$(RESORT_DATABASE_URL="$DATABASE_URL_VALUE" python3 -c '
import os
from urllib.parse import urlparse
url = os.environ["RESORT_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
print(urlparse(url).password)
')
export DB_PASSWORD

# مراجعة Codex 2026-08-31 (SEC-08): كان مقفول على IP السيرفر القديم
# (191.218.161.133) — الشهادة الحقيقية دلوقتي domain-based (elkheima.com،
# راجع docs/agent-workflow/handoffs/2026-08-30_REL-23-REL-24_production-
# deploy_claude_handoff.md). ip-only هو fallback bootstrap أول مرة قبل أي
# شهادة (راجع deploy/nginx/edge-ip-only.conf).
if [[ -f /etc/letsencrypt/live/elkheima.com/fullchain.pem ]]; then
  OVERRIDE=docker-compose.prod.domain.yml
else
  OVERRIDE=docker-compose.prod.ip-only.yml
fi

sudo -E docker compose --env-file backend/.env.prod -f docker-compose.prod.yml -f "$OVERRIDE" exec -T backend \
  python -m app.admin_bootstrap create --email "$EMAIL" --full-name "$FULL_NAME" <<STDIN_EOF
$EMAIL
STDIN_EOF
