#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Resort OS — Start Dev Environment
#  Usage: bash start.sh [--no-frontend] [--no-worker] [--apps="admin pos"]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/backend/.venv"
LOG_DIR="/tmp"
PREFIX="resort-os"

# ── Flags ─────────────────────────────────────────────────────────────────────
START_FRONTEND=true
START_WORKER=true
# 2026-07-01: pos/kds/ops/admin/waiter/portal merged into a single `el-kheima`
# app (frontend/apps/el-kheima, port 3001, package name `el-kheima` — briefly
# called `staff` mid-merge, renamed to match the project's brand name "El
# Kheima Beach") — one login, one build, client-side role/module gating in
# the router instead of 6 separate SPAs. `qr` and `public` stay separate
# (unauthenticated, different audience/security model).
APPS="el-kheima qr public"
for arg in "$@"; do
  case "$arg" in
    --no-frontend) START_FRONTEND=false ;;
    --no-worker)   START_WORKER=false ;;
    --apps=*)      APPS="${arg#--apps=}" ;;
  esac
done

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN="\033[0;32m"; CYAN="\033[0;36m"; YELLOW="\033[1;33m"
RED="\033[0;31m"; GOLD="\033[0;33m"; NC="\033[0m"
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
info() { echo -e "${CYAN}  → $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
err()  { echo -e "${RED}  ✗ $*${NC}" >&2; exit 1; }

declare -A APP_PORTS=(
  [el-kheima]=3001 [qr]=3005 [public]=3007
)

echo -e "${GOLD}
╔══════════════════════════════════════════════════════╗
║          🏖️  Resort OS — Starting Dev Environment     ║
║                  WegoSharm · شرم الشيخ               ║
╚══════════════════════════════════════════════════════╝${NC}
"

# ── Guards ────────────────────────────────────────────────────────────────────
[[ -f "$ROOT/backend/.env" ]]          || err ".env not found — copy: cp backend/.env.example backend/.env"
[[ -d "$VENV" ]]                       || err "Python venv missing — run: cd backend && make install"
[[ -d "$ROOT/frontend/node_modules" ]] || warn "Frontend node_modules missing — run: cd frontend && pnpm install"

# ── Docker: PostgreSQL + Redis ───────────────────────────────────────────────
info "Starting PostgreSQL (Docker :5436) + Redis (Docker :6381)..."
if ! docker compose -f "$ROOT/docker-compose.yml" up -d 2>&1 | grep -qE "error|Error"; then
  :
else
  docker start resort-os-db_postgres-1 resort-os-redis_cache-1 2>/dev/null || true
fi

for i in $(seq 1 30); do
  if pg_isready -h 127.0.0.1 -p 5436 -q 2>/dev/null; then
    ok "PostgreSQL ready (resort_os)"
    break
  fi
  [[ $i -eq 30 ]] && err "PostgreSQL not ready after 30s\n  Debug: docker logs resort-os-db_postgres-1"
  sleep 1
done

if redis-cli -p 6381 ping 2>/dev/null | grep -q PONG; then
  ok "Redis ready (port 6381)"
else
  warn "Redis not responding on 6381 — caching/celery disabled (non-fatal)"
fi

# ── Kill stale processes ──────────────────────────────────────────────────────
fuser -k 8005/tcp 2>/dev/null && echo -e "  ${YELLOW}⏹  Killed old backend (8005)${NC}" || true
for app in $APPS; do
  fuser -k "${APP_PORTS[$app]}/tcp" 2>/dev/null && echo -e "  ${YELLOW}⏹  Killed old $app (${APP_PORTS[$app]})${NC}" || true
done
pkill -f "celery -A app.celery_app" 2>/dev/null && echo -e "  ${YELLOW}⏹  Killed old Celery processes${NC}" || true
sleep 1

# ── Load .env + venv ──────────────────────────────────────────────────────────
set -a; source "$ROOT/backend/.env"; set +a
source "$VENV/bin/activate"

# ── Migrations ────────────────────────────────────────────────────────────────
info "Running database migrations..."
cd "$ROOT/backend"
alembic upgrade head 2>&1 | grep -v "^$" | sed 's/^/    /' || warn "Migration issue — check logs"
ok "Migrations up to date"

# ── Seed (first run only) ─────────────────────────────────────────────────────
USER_COUNT=$(python3 -c "
from app.core.database import SessionLocal
from app.core.kernel.models.user import User
db = SessionLocal()
print(db.query(User).count())
db.close()
" 2>/dev/null || echo "99")

if [[ "$USER_COUNT" -eq 0 ]]; then
  info "First run — seeding branch + admin + reference data..."
  python3 -m app.seed 2>&1 | sed 's/^/    /'
  ok "Seed complete"
fi

# ── Start Backend ─────────────────────────────────────────────────────────────
info "Starting backend (port 8005)..."
cd "$ROOT/backend"
nohup python -m uvicorn app.main:app --reload --port 8005 --host 127.0.0.1 \
  > "$LOG_DIR/$PREFIX-backend.log" 2>&1 &
echo $! > "$LOG_DIR/$PREFIX-backend.pid"
ok "Backend started (PID: $(cat "$LOG_DIR/$PREFIX-backend.pid"))"

# ── Start Celery worker + beat ────────────────────────────────────────────────
if $START_WORKER; then
  info "Starting Celery worker..."
  nohup python -m celery -A app.celery_app worker --loglevel=info --concurrency=4 \
    > "$LOG_DIR/$PREFIX-worker.log" 2>&1 &
  echo $! > "$LOG_DIR/$PREFIX-worker.pid"
  ok "Celery worker started (PID: $(cat "$LOG_DIR/$PREFIX-worker.pid"))"

  info "Starting Celery beat (scheduler)..."
  nohup python -m celery -A app.celery_app beat --loglevel=info \
    > "$LOG_DIR/$PREFIX-beat.log" 2>&1 &
  echo $! > "$LOG_DIR/$PREFIX-beat.pid"
  ok "Celery beat started (PID: $(cat "$LOG_DIR/$PREFIX-beat.pid"))"
fi

# ── Start Frontend apps ────────────────────────────────────────────────────────
if $START_FRONTEND && [[ -d "$ROOT/frontend/node_modules" ]]; then
  for app in $APPS; do
    info "Starting $app (port ${APP_PORTS[$app]})..."
    cd "$ROOT/frontend"
    nohup pnpm --filter "$app" dev > "$LOG_DIR/$PREFIX-fe-$app.log" 2>&1 &
    echo $! > "$LOG_DIR/$PREFIX-fe-$app.pid"
  done
  ok "Frontend apps launched: $APPS"
elif $START_FRONTEND; then
  warn "Frontend skipped — node_modules missing (run: cd frontend && pnpm install)"
fi

# ── Health check ──────────────────────────────────────────────────────────────
echo -n -e "\n  ${CYAN}→ Waiting for backend${NC}"
for i in $(seq 1 20); do
  if curl -s http://127.0.0.1:8005/health > /dev/null 2>&1; then
    echo " ✅"
    break
  fi
  echo -n "."
  sleep 1
  [[ $i -eq 20 ]] && echo -e " ${YELLOW}(timeout — check logs)${NC}"
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "${GOLD}
  ════════════════════════════════════════════${NC}"

BACKEND_UP=false
curl -s http://127.0.0.1:8005/health > /dev/null 2>&1 && BACKEND_UP=true

if $BACKEND_UP; then
  echo -e "${GREEN}  ✓  Backend:   http://127.0.0.1:8005${NC}"
  echo -e "${GREEN}  ✓  API Docs:  http://127.0.0.1:8005/docs${NC}"
else
  echo -e "${RED}  ✗  Backend not responding — tail -f $LOG_DIR/$PREFIX-backend.log${NC}"
fi

if $START_WORKER; then
  echo -e "${GREEN}  ✓  Celery worker + beat running${NC}"
fi

if $START_FRONTEND; then
  for app in $APPS; do
    echo -e "${GREEN}  ✓  ${app}:$(printf '%*s' $((8 - ${#app})) '')http://127.0.0.1:${APP_PORTS[$app]}${NC}"
  done
fi

echo -e "
  ${CYAN}🔑  admin@resortos.local / Admin@123456${NC}

  ${GOLD}Logs:${NC}   tail -f $LOG_DIR/$PREFIX-backend.log
          tail -f $LOG_DIR/$PREFIX-fe-el-kheima.log   (etc. per app)
  ${GOLD}Status:${NC} ./status.sh
  ${GOLD}Stop:${NC}   ./stop.sh
"
