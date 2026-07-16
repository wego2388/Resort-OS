#!/usr/bin/env bash
# =============================================================================
#  Resort OS — Start Dev Environment
#  Usage: bash scripts/start.sh [--no-frontend] [--no-worker] [--apps="el-kheima public"]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
PID_DIR="$ROOT/.pids"
LOG_DIR="$BACKEND/logs"

mkdir -p "$PID_DIR" "$LOG_DIR"

# ── Flags ─────────────────────────────────────────────────────────────────────
START_FRONTEND=true
START_WORKER=true
# 2026-07-01: pos/kds/ops/admin/waiter/portal merged into a single `el-kheima`
# app (frontend/apps/el-kheima, port 3001) — one login, one build, client-side
# role/module gating in the router instead of 6 separate SPAs. `public` stays
# separate (unauthenticated, different audience/security model) — it also
# absorbed the old `qr` app (2026-07-06): both were unauthenticated
# guest-facing apps, no reason to ship/deploy them as two separate SPAs.
APPS="el-kheima public"
for arg in "$@"; do
  case "$arg" in
    --no-frontend) START_FRONTEND=false ;;
    --no-worker)   START_WORKER=false ;;
    --apps=*)      APPS="${arg#--apps=}" ;;
  esac
done

# ── Colors ────────────────────────────────────────────────────────────────────
BOLD=$'\e[1m'; RESET=$'\e[0m'
CYAN=$'\e[36m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; GOLD=$'\e[33m'; DIM=$'\e[2m'
ok()   { echo "  ${GREEN}✓${RESET} $*"; }
info() { echo "  ${CYAN}→${RESET} $*"; }
warn() { echo "  ${YELLOW}⚠${RESET}  $*"; }
die()  { echo "  ${RED}✗${RESET} $*"; exit 1; }

declare -A APP_PORTS=( [el-kheima]=3001 [public]=3007 )

echo
echo "${GOLD}${BOLD}╔══════════════════════════════════════════════════════╗${RESET}"
echo "${GOLD}${BOLD}║          🏖️  Resort OS — Starting Dev Environment     ║${RESET}"
echo "${GOLD}${BOLD}║                  El Kheima Beach · شرم الشيخ          ║${RESET}"
echo "${GOLD}${BOLD}╚══════════════════════════════════════════════════════╝${RESET}"
echo

# ── Guard: already running? ───────────────────────────────────────────────────
# ⚠️ لازم نتحقق من البورت الفعلي (fuser) مش بس ملف الـ PID — باج حقيقي كان
# هنا: لو حد شغّل uvicorn يدويًا برّه النظام ده (أو وكيل/جلسة تانية) وما
# اتسجّلش في .pids/، الفحص القديم (PID file بس) كان بيفشل يلاحظه، فـ
# start.sh كان بيحاول يشغّل نسخة جديدة تتصادم على نفس البورت وتطيح بـ
# "Address already in use" — لكن health check كان لسه بينجح (بيضرب على
# النسخة القديمة الشغالة فعلًا)، فالسكريبت كان بيبلّغ "نجح" رغم إن النسخة
# اللي هو فعلاً شغّلها ماتت فورًا. اتصلح بفحص البورت مباشرة.
if [[ -f "$PID_DIR/backend.pid" ]] && kill -0 "$(cat "$PID_DIR/backend.pid")" 2>/dev/null; then
  warn "Backend already running (PID $(cat "$PID_DIR/backend.pid")) — run scripts/stop.sh first, or scripts/restart.sh"
  exit 1
fi
if fuser 8005/tcp >/dev/null 2>&1; then
  die "Port 8005 already in use by an untracked process (not started via this script) — find it with: lsof -i :8005  — then kill it or run: fuser -k 8005/tcp"
fi

# ── Pre-flight guards ──────────────────────────────────────────────────────────
[[ -f "$BACKEND/.env" ]]          || die ".env not found — copy: cp backend/.env.example backend/.env"
[[ -d "$VENV" ]]                  || die "Python venv missing — run: cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
[[ -d "$FRONTEND/node_modules" ]] || warn "Frontend node_modules missing — run: cd frontend && pnpm install"

# ── Docker: PostgreSQL + Redis ───────────────────────────────────────────────
info "Starting PostgreSQL (Docker :5436) + Redis (Docker :6381)..."
docker compose -f "$ROOT/docker-compose.yml" up -d 2>&1 | sed 's/^/    /' || true

for i in $(seq 1 30); do
  if pg_isready -h 127.0.0.1 -p 5436 -q 2>/dev/null; then
    ok "PostgreSQL ready (resort_os)"
    break
  fi
  [[ $i -eq 30 ]] && die "PostgreSQL not ready after 30s — debug: docker logs resort-os-db_postgres-1"
  sleep 1
done

if redis-cli -p 6381 ping 2>/dev/null | grep -q PONG; then
  ok "Redis ready (port 6381)"
else
  warn "Redis not responding on 6381 — caching/celery disabled (non-fatal)"
fi

# ── Load .env + venv ──────────────────────────────────────────────────────────
set -a; source "$BACKEND/.env"; set +a
source "$VENV/bin/activate"

# ── Migrations ────────────────────────────────────────────────────────────────
info "Running database migrations..."
cd "$BACKEND"
alembic upgrade head 2>&1 | grep -v "^$" | sed 's/^/    /' || warn "Migration issue — check output above"
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
  info "First run — seeding branch, reference data, and demo accounts (one per role)..."
  python3 -m app.seed 2>&1 | sed 's/^/    /'
  ok "Seed complete — see scripts/status.sh or CLAUDE.md for demo login credentials"
fi

# ── Start Backend ─────────────────────────────────────────────────────────────
info "Starting backend (port 8005)..."
cd "$BACKEND"
: > "$LOG_DIR/api.log"   # truncate — avoids reading a stale bind-error from a previous run below
nohup python -m uvicorn app.main:app --reload --port 8005 --host 0.0.0.0 \
  > "$LOG_DIR/api.log" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$PID_DIR/backend.pid"

# Real bind-failure detection — a dead PID a few hundred ms later means
# uvicorn exited immediately (almost always "Address already in use").
# Don't just trust `echo $!` + a later health-check ever having found
# *something* on the port; verify *this* process is the one actually
# serving it.
sleep 0.5
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  rm -f "$PID_DIR/backend.pid"
  echo "  ${RED}✗${RESET} Backend process died immediately — real error from $LOG_DIR/api.log:"
  tail -5 "$LOG_DIR/api.log" | sed 's/^/    /'
  exit 1
fi
ok "Backend started (PID $BACKEND_PID)"

# ── Start Celery worker + beat ────────────────────────────────────────────────
if $START_WORKER; then
  info "Starting Celery worker..."
  nohup python -m celery -A app.celery_app worker --loglevel=info --concurrency=4 \
    > "$LOG_DIR/celery.log" 2>&1 &
  echo $! > "$PID_DIR/celery.pid"
  ok "Celery worker started (PID $(cat "$PID_DIR/celery.pid"))"

  info "Starting Celery beat (scheduler)..."
  nohup python -m celery -A app.celery_app beat --loglevel=info \
    > "$LOG_DIR/celery_beat.log" 2>&1 &
  echo $! > "$PID_DIR/celery_beat.pid"
  ok "Celery beat started (PID $(cat "$PID_DIR/celery_beat.pid"))"
fi

# ── Start Frontend apps ────────────────────────────────────────────────────────
if $START_FRONTEND && [[ -d "$FRONTEND/node_modules" ]]; then
  for app in $APPS; do
    info "Starting $app (port ${APP_PORTS[$app]})..."
    cd "$FRONTEND"
    nohup pnpm --filter "$app" dev > "$LOG_DIR/frontend-$app.log" 2>&1 &
    echo $! > "$PID_DIR/frontend-$app.pid"
  done
  ok "Frontend apps launched: $APPS"
elif $START_FRONTEND; then
  warn "Frontend skipped — node_modules missing (run: cd frontend && pnpm install)"
fi

# ── Health check ──────────────────────────────────────────────────────────────
echo -n -e "\n  ${CYAN}→ Waiting for backend${RESET}"
BACKEND_UP=false
for i in $(seq 1 20); do
  if curl -s http://127.0.0.1:8005/health > /dev/null 2>&1; then
    echo " ✅"; BACKEND_UP=true; break
  fi
  echo -n "."; sleep 1
  [[ $i -eq 20 ]] && echo " ${YELLOW}(timeout — check scripts/logs.sh api)${RESET}"
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo
echo "${GOLD}${BOLD}  ════════════════════════════════════════════${RESET}"

if $BACKEND_UP; then
  echo "  ${GREEN}✓  Backend:   http://127.0.0.1:8005${RESET}"
  echo "  ${GREEN}✓  API Docs:  http://127.0.0.1:8005/docs${RESET}"
else
  echo "  ${RED}✗  Backend not responding — scripts/logs.sh api${RESET}"
fi

$START_WORKER && echo "  ${GREEN}✓  Celery worker + beat running${RESET}"

if $START_FRONTEND; then
  for app in $APPS; do
    printf "  ${GREEN}✓  %-10s http://127.0.0.1:%s${RESET}\n" "$app:" "${APP_PORTS[$app]}"
  done
fi

echo
echo "  ${CYAN}🔑  Demo accounts — see: ${BOLD}scripts/status.sh${RESET}${CYAN} or CLAUDE.md${RESET}"
echo
echo "  ${GOLD}Logs:${RESET}    bash scripts/logs.sh [api|celery|beat|frontend-<app>]"
echo "  ${GOLD}Status:${RESET}  bash scripts/status.sh"
echo "  ${GOLD}Stop:${RESET}    bash scripts/stop.sh"
echo "  ${GOLD}Restart:${RESET} bash scripts/restart.sh"
echo
