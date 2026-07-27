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

cd /opt/resort-os

DATABASE_URL_VALUE=$(grep -E '^DATABASE_URL=' backend/.env.prod | head -1 | cut -d= -f2-)
DB_PASSWORD=$(RESORT_DATABASE_URL="$DATABASE_URL_VALUE" python3 -c '
import os
from urllib.parse import urlparse
url = os.environ["RESORT_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
print(urlparse(url).password)
')
export DB_PASSWORD

TLS_CERT_PATH=/etc/letsencrypt/live/191.218.161.133/fullchain.pem
if [[ -f "$TLS_CERT_PATH" ]]; then
  OVERRIDE=docker-compose.prod.ip-tls.yml
else
  OVERRIDE=docker-compose.prod.ip-only.yml
fi

sudo -E docker compose --env-file backend/.env.prod -f docker-compose.prod.yml -f "$OVERRIDE" exec -T backend \
  python -m app.admin_bootstrap create --email "$EMAIL" --full-name "$FULL_NAME" <<STDIN_EOF
$EMAIL
STDIN_EOF
