#!/usr/bin/env bash
# =============================================================================
#  Resort OS — Stop Dev Environment
#  Usage: bash scripts/stop.sh [--docker]
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PID_DIR="$ROOT/.pids"

BOLD=$'\e[1m'; RESET=$'\e[0m'
GREEN=$'\e[32m'; YELLOW=$'\e[33m'; DIM=$'\e[2m'
ok()   { echo "  ${GREEN}✓${RESET} $*"; }
info() { echo "  ${YELLOW}⏹${RESET}  $*"; }

echo
echo "${YELLOW}${BOLD}  🛑 Resort OS — Stopping...${RESET}"
echo

stop_by_pidfile() {
  local name="$1" pid_file="$PID_DIR/$2"
  if [[ -f "$pid_file" ]]; then
    local pid; pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null
      sleep 0.3
      kill -9 "$pid" 2>/dev/null || true
      ok "$name stopped (was PID $pid)"
    else
      info "$name — stale PID file (process already gone)"
    fi
    rm -f "$pid_file"
  else
    echo "  ${DIM}$name was not running${RESET}"
  fi
}

stop_by_pidfile "Backend" "backend.pid"
stop_by_pidfile "Celery worker" "celery.pid"
stop_by_pidfile "Celery beat" "celery_beat.pid"

for f in "$PID_DIR"/frontend-*.pid; do
  [[ -f "$f" ]] || continue
  app="$(basename "$f" .pid | sed 's/^frontend-//')"
  stop_by_pidfile "Frontend ($app)" "$(basename "$f")"
done

# Safety net: kill anything still bound to known ports (covers processes
# started outside this script, e.g. a previous session's start.sh at root).
for port in 8005 3001 3005 3007; do
  fuser -k "${port}/tcp" 2>/dev/null && info "Killed stray process on port $port" || true
done
pkill -f "celery -A app.celery_app" 2>/dev/null && info "Killed stray Celery processes" || true

# ── Optionally stop Docker too ────────────────────────────────────────────────
if [[ "${1:-}" == "--docker" ]]; then
  echo "  → Stopping Docker services..."
  docker compose -f "$ROOT/docker-compose.yml" down
  ok "Docker stopped"
else
  echo "  ${DIM}Docker DB+Redis left running (use: scripts/stop.sh --docker to stop)${RESET}"
fi

echo
ok "Done"
echo
