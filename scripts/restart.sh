#!/usr/bin/env bash
# =============================================================================
#  Resort OS — Restart Dev Environment
#  Usage: bash scripts/restart.sh [same flags as scripts/start.sh]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/stop.sh"
echo
sleep 1
bash "$SCRIPT_DIR/start.sh" "$@"
