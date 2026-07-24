#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  deploy.sh — Resort OS production deploy script
#  شغّله على الـ VPS:  bash scripts/deploy.sh
#
#  ما بيعمله:
#    1. نسخة احتياطية قبل التغيير
#    2. تحديث fast-forward للفرع الحالي/المحدد فقط
#    3. بناء الصور وتشغيل migrations قبل استبدال الخدمات
#    4. تشغيل الـ containers باختيار HTTP أو IP TLS تلقائيًا
#    5. التحقق من صحة الـ backend والحاويات
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$REPO_DIR/docker-compose.prod.yml"
ENV_FILE="$REPO_DIR/backend/.env.prod"
IP_CERT="$([ -n "${RESORT_IP_ADDRESS:-}" ] && printf '%s' "$RESORT_IP_ADDRESS" || printf '%s' '187.124.170.249')"
TLS_CERT_PATH="/etc/letsencrypt/live/$IP_CERT/fullchain.pem"

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

# ── Preconditions ─────────────────────────────────────────────────────────
[[ -f "$ENV_FILE" ]] || err "$ENV_FILE غير موجود"
[[ -z "$(git status --porcelain)" ]] || err "الـ worktree فيه تغييرات غير محفوظة — أوقف النشر وراجعها"

DEPLOY_BRANCH="${DEPLOY_BRANCH:-$(git branch --show-current)}"
[[ -n "$DEPLOY_BRANCH" ]] || err "لا يمكن النشر من detached HEAD — حدد DEPLOY_BRANCH"

if [[ -f "$TLS_CERT_PATH" ]]; then
  COMPOSE_OVERRIDE="$REPO_DIR/docker-compose.prod.ip-tls.yml"
  log "سيُستخدم IP TLS certificate لـ $IP_CERT"
else
  COMPOSE_OVERRIDE="$REPO_DIR/docker-compose.prod.ip-only.yml"
  warn "لا توجد شهادة IP بعد؛ سيستمر HTTP مؤقتًا لإتمام ACME"
fi

COMPOSE=(docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_OVERRIDE")

# ── 1. Backup before code/schema changes ──────────────────────────────────
log "Step 1/5 — نسخة PostgreSQL احتياطية"
ENV_FILE="$ENV_FILE" "$REPO_DIR/scripts/backup_db.sh" || err "النسخ الاحتياطي فشل"

# ── 2. Fast-forward the selected branch ───────────────────────────────────
log "Step 2/5 — تحديث origin/$DEPLOY_BRANCH"
git fetch origin "$DEPLOY_BRANCH" || err "git fetch فشل"
git merge --ff-only "origin/$DEPLOY_BRANCH" || err "التحديث ليس fast-forward؛ لا نشر تلقائي"

CURRENT_COMMIT=$(git log --oneline -1)
log "آخر commit: $CURRENT_COMMIT"

# ── 3. docker compose build ───────────────────────────────────────────────
log "Step 3/5 — docker compose build (قد يأخذ دقيقتين...)"
"${COMPOSE[@]}" build --parallel || err "docker build فشل"

# ── 4. Migrate first, then replace services ───────────────────────────────
log "Step 4/5 — تطبيق migrations ثم تشغيل الخدمات"
"${COMPOSE[@]}" run --rm backend alembic upgrade head || err "alembic upgrade head فشل"
"${COMPOSE[@]}" up -d || err "docker compose up فشل"

# انتظر الـ backend يصحى
log "انتظار الـ backend (max 60 ثانية)..."
for i in $(seq 1 30); do
    if "${COMPOSE[@]}" exec -T backend \
        curl -fsS http://127.0.0.1:8005/health >/dev/null 2>&1; then
        break
    fi
    sleep 2
    if [[ $i -eq 30 ]]; then
        warn "الـ backend تأخر في البداية — جرب تشوف اللوجات"
    fi
done

# ── تحقق نهائي ────────────────────────────────────────────────────────────
log "Step 5/5 — فحص الصحة والحاويات"
"${COMPOSE[@]}" exec -T backend curl -fsS http://127.0.0.1:8005/health >/dev/null \
  || err "Health check فشل — راجع logs backend"
"${COMPOSE[@]}" ps
log "Health check: OK"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Deploy اكتمل بنجاح 🚀"
echo ""
echo "  للتحقق من اللوجات:"
echo "  docker compose -f $COMPOSE_FILE -f $COMPOSE_OVERRIDE logs backend --tail=100 -f"
echo ""
echo "  للتحقق من حالة الـ containers:"
echo "  docker compose -f $COMPOSE_FILE -f $COMPOSE_OVERRIDE ps"
