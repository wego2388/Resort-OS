#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  sync-deploy.sh — نشر مستهدف للـ VPS من worktree غير committed
#
#  متى تستخدمه بدل deploy.sh:
#    deploy.sh بيفترض إن الكود متعمله commit على origin وبيعمل git pull +
#    build/restart لكل الخدمات. النشر الحالي شغال بنموذج "exact source
#    worktree transfer" (بدون git على السيرفر) — استخدم السكريبت ده لما
#    عايز تنشر تعديلات محلية غير committed على خدمة أو اتنين بس، من غير
#    ما تلمس .env.prod أو تعمل rebuild لحاجة مش محتاجة تتغير.
#
#  ما بيعمله:
#    1. rsync إضافي فقط (بدون --delete) لمجلد المشروع المحلي (resort-os أو
#       marketing) لنفس المسار على الـ VPS — باستبعاد .env*، .git،
#       node_modules، dist، __pycache__، backups، logs. متعمّد إنه ميحذفش
#       ملفات موجودة على الـ VPS بس مش موجودة محليًا (زي uploads أو ملفات
#       مولّدة على السيرفر) — لو محتاج mirror كامل مع حذف، اعمله يدويًا بوعي
#    2. اشتقاق DB_PASSWORD من backend/.env.prod (بنفس منطق deploy.sh
#       بالظبط) بدون طباعته أبدًا
#    3. docker compose build للـ service(s) المحددة بس
#    4. docker compose up -d --no-deps لنفس الـ service(s)
#    5. فحص أساسي: حالة الحاويات + curl على localhost
#
#  حدود متعمّدة (مش بديل كامل لـ deploy.sh):
#    - مفيش نسخة احتياطية تلقائية للداتابيز
#    - مفيش alembic migrations — لو تعديلك فيه migration، استخدم deploy.sh
#      بعد ما الكود يتعمله commit، أو شغّل الـ migration يدويًا بوعي
#    - بيفترض إن docker-compose.prod.yml + override التبع (ip-tls/ip-only)
#      موجودين بالفعل على الـ VPS في /opt/resort-os
#
#  الاستخدام:
#    scripts/sync-deploy.sh <resort-os|marketing> <service1[,service2,...]>
#
#  أمثلة:
#    scripts/sync-deploy.sh resort-os el_kheima
#    scripts/sync-deploy.sh marketing marketing_site
#    scripts/sync-deploy.sh resort-os el_kheima,backend
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SSH_HOST="${RESORT_VPS_SSH_HOST:-resort-os-vps}"
REMOTE_RESORT_DIR="/opt/resort-os"
REMOTE_MARKETING_DIR="/opt/elkheima-marketing-website"
LOCAL_RESORT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_MARKETING_DIR="$(cd "$LOCAL_RESORT_DIR/../elkheima-marketing-website" && pwd)"
TLS_CERT_NAME="${RESORT_TLS_NAME:-191.218.161.133}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✅ $*${NC}"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠️  $*${NC}"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')] ❌ $*${NC}"; exit 1; }

[[ $# -eq 2 ]] || { echo "Usage: $0 <resort-os|marketing> <service1[,service2,...]>"; exit 1; }
PROJECT="$1"
SERVICES_CSV="$2"
read -r -a SERVICES <<< "${SERVICES_CSV//,/ }"

case "$PROJECT" in
  resort-os)
    LOCAL_DIR="$LOCAL_RESORT_DIR"
    REMOTE_DIR="$REMOTE_RESORT_DIR"
    ;;
  marketing)
    LOCAL_DIR="$LOCAL_MARKETING_DIR"
    REMOTE_DIR="$REMOTE_MARKETING_DIR"
    ;;
  *) err "أول argument لازم يكون resort-os أو marketing (استلمت: $PROJECT)" ;;
esac

[[ -d "$LOCAL_DIR" ]] || err "$LOCAL_DIR غير موجود محليًا"

log "Sync-Deploy بدأ — project=$PROJECT services=${SERVICES[*]}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Rsync (استبعاد الأسرار والملفات المولّدة/المؤقتة) ───────────────────
log "Step 1/4 — rsync $LOCAL_DIR/ → $SSH_HOST:$REMOTE_DIR/"
rsync -avz \
  --exclude '.env*' \
  --exclude '.git/' \
  --exclude '.claude/' \
  --exclude 'node_modules/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'dist/' \
  --exclude '.venv/' \
  --exclude '.pytest_cache/' \
  --exclude 'backups/' \
  --exclude 'logs/' \
  --exclude '*.log' \
  --exclude 'celerybeat-schedule' \
  --exclude '*.db' \
  --rsh=ssh \
  "$LOCAL_DIR"/ "$SSH_HOST:$REMOTE_DIR"/ \
  || err "rsync فشل"

# ── 2. اشتقاق DB_PASSWORD (بنفس منطق deploy.sh) + build على الـ VPS ───────
log "Step 2/4 — build ${SERVICES[*]} على الـ VPS"
# shellcheck disable=SC2029
ssh "$SSH_HOST" "cd '$REMOTE_RESORT_DIR' && \
  DATABASE_URL_VALUE=\$(grep -E '^DATABASE_URL=' backend/.env.prod | head -1 | cut -d= -f2-) && \
  DB_PASSWORD=\$(RESORT_DATABASE_URL=\"\$DATABASE_URL_VALUE\" python3 -c '
import os
from urllib.parse import urlparse
url = os.environ[\"RESORT_DATABASE_URL\"].replace(\"postgresql+psycopg://\", \"postgresql://\", 1)
password = urlparse(url).password
if not password:
    raise SystemExit(\"DATABASE_URL has no password\")
print(password)
') && \
  export DB_PASSWORD && \
  TLS_CERT_PATH=/etc/letsencrypt/live/${TLS_CERT_NAME}/fullchain.pem && \
  if [[ -f \"\$TLS_CERT_PATH\" ]]; then OVERRIDE=docker-compose.prod.ip-tls.yml; else OVERRIDE=docker-compose.prod.ip-only.yml; fi && \
  sudo -E docker compose --env-file backend/.env.prod -f docker-compose.prod.yml -f \"\$OVERRIDE\" build ${SERVICES[*]}" \
  || err "docker build فشل على الـ VPS"

# ── 3. استبدال الـ service(s) المحددة بس ────────────────────────────────
log "Step 3/4 — up -d --no-deps ${SERVICES[*]}"
# shellcheck disable=SC2029
ssh "$SSH_HOST" "cd '$REMOTE_RESORT_DIR' && \
  DATABASE_URL_VALUE=\$(grep -E '^DATABASE_URL=' backend/.env.prod | head -1 | cut -d= -f2-) && \
  DB_PASSWORD=\$(RESORT_DATABASE_URL=\"\$DATABASE_URL_VALUE\" python3 -c '
import os
from urllib.parse import urlparse
url = os.environ[\"RESORT_DATABASE_URL\"].replace(\"postgresql+psycopg://\", \"postgresql://\", 1)
password = urlparse(url).password
if not password:
    raise SystemExit(\"DATABASE_URL has no password\")
print(password)
') && \
  export DB_PASSWORD && \
  TLS_CERT_PATH=/etc/letsencrypt/live/${TLS_CERT_NAME}/fullchain.pem && \
  if [[ -f \"\$TLS_CERT_PATH\" ]]; then OVERRIDE=docker-compose.prod.ip-tls.yml; else OVERRIDE=docker-compose.prod.ip-only.yml; fi && \
  sudo -E docker compose --env-file backend/.env.prod -f docker-compose.prod.yml -f \"\$OVERRIDE\" up -d --no-deps ${SERVICES[*]}" \
  || err "docker compose up فشل على الـ VPS"

# ── 4. فحص أساسي ─────────────────────────────────────────────────────────
log "Step 4/4 — فحص الحاويات"
sleep 5
ssh "$SSH_HOST" "sudo docker ps --filter 'name=resort-os-prod' --format 'table {{.Names}}\t{{.Status}}'"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Sync-Deploy اكتمل — ${SERVICES[*]} اتبنت واتعمللها restart"
warn "تحقق يدويًا (curl على الدومين/الـ IP الفعلي + افتح الصفحة في المتصفح) قبل ما تعتبرها خلصت فعليًا"
warn "السكريبت ده بديل مؤقت لـ deploy.sh — من غير backup تلقائي أو migrations. لو تعديلك فيه migration استخدم deploy.sh بعد commit، أو شغّل alembic يدويًا بوعي"
