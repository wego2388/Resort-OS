#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  deploy.sh — Resort OS production deploy script
#  شغّله على الـ VPS:  bash scripts/deploy.sh
#
#  ما بيعمله:
#    1. git pull — جلب آخر الكود
#    2. docker compose build — بناء الـ images الجديدة
#    3. docker compose up -d — تشغيل الـ containers بدون downtime
#    4. alembic upgrade head — تطبيق الـ migrations الجديدة
#    5. التحقق من صحة الـ backend
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
COMPOSE_OVERRIDE="docker-compose.prod.ip-only.yml"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✅ $*${NC}"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠️  $*${NC}"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')] ❌ $*${NC}"; exit 1; }

cd "$REPO_DIR"
log "Deploy بدأ — $(date)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. git pull ────────────────────────────────────────────────────────────
log "Step 1/5 — git pull"
git pull origin main || err "git pull فشل"

CURRENT_COMMIT=$(git log --oneline -1)
log "آخر commit: $CURRENT_COMMIT"

# ── 2. تحقق من وجود .env ──────────────────────────────────────────────────
if [[ ! -f "backend/.env" ]]; then
    err "backend/.env غير موجود — انسخه من backend/.env.example وعدّل القيم"
fi
log "Step 2/5 — .env موجود ✓"

# ── 3. docker compose build ───────────────────────────────────────────────
log "Step 3/5 — docker compose build (قد يأخذ دقيقتين...)"
docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_OVERRIDE" build --parallel || err "docker build فشل"

# ── 4. docker compose up -d ───────────────────────────────────────────────
log "Step 4/5 — تشغيل الـ containers"
docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_OVERRIDE" up -d || err "docker compose up فشل"

# انتظر الـ backend يصحى
log "انتظار الـ backend (max 60 ثانية)..."
for i in $(seq 1 30); do
    if docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_OVERRIDE" exec -T backend \
        python -c "import app.main" 2>/dev/null; then
        break
    fi
    sleep 2
    if [[ $i -eq 30 ]]; then
        warn "الـ backend تأخر في البداية — جرب تشوف اللوجات"
    fi
done

# ── 5. alembic upgrade head ───────────────────────────────────────────────
log "Step 5/5 — تطبيق الـ DB migrations"
docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_OVERRIDE" exec -T backend \
    alembic upgrade head || err "alembic upgrade head فشل — راجع اللوجات"

# ── تحقق نهائي ────────────────────────────────────────────────────────────
log "التحقق من الـ health endpoint..."
sleep 3

HEALTH=$(docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_OVERRIDE" exec -T backend \
    python -c "
import urllib.request, sys
try:
    r = urllib.request.urlopen('http://localhost:8000/health', timeout=5)
    print(r.read().decode()[:50])
    sys.exit(0)
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
" 2>&1) || true

if echo "$HEALTH" | grep -qi "ok\|healthy\|true"; then
    log "Health check: OK"
else
    warn "Health endpoint لم يرد — تحقق يدوياً:"
    warn "docker compose -f $COMPOSE_FILE logs backend --tail=50"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Deploy اكتمل بنجاح 🚀"
echo ""
echo "  للتحقق من اللوجات:"
echo "  docker compose -f $COMPOSE_FILE logs backend --tail=100 -f"
echo ""
echo "  للتحقق من حالة الـ containers:"
echo "  docker compose -f $COMPOSE_FILE ps"
