#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  switch-to-domain.sh — تحويل من IP-TLS إلى domain-based TLS
#  يشتغل على VPS بعد انتشار DNS لـ elkheima.com
#
#  الاستخدام:
#    bash scripts/switch-to-domain.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DOMAIN="elkheima.com"
APP_DOMAIN="app.elkheima.com"
EMAIL="theagaty@gmail.com"
PROJECT_DIR="/opt/resort-os"

cd "$PROJECT_DIR"

echo "=== [1/5] التحقق من انتشار DNS ==="
RESOLVED_APEX=$(dig "$DOMAIN" A @1.1.1.1 +short | head -1)
RESOLVED_APP=$(dig "$APP_DOMAIN" A @1.1.1.1 +short | head -1)

if [[ "$RESOLVED_APEX" != "191.218.161.133" ]]; then
    echo "❌ $DOMAIN لسه مش بيحل على 191.218.161.133 (حالياً: $RESOLVED_APEX)"
    echo "   انتظر انتشار الـ DNS وشغّل السكريبت تاني."
    exit 1
fi

if [[ "$RESOLVED_APP" != "191.218.161.133" ]]; then
    echo "❌ $APP_DOMAIN لسه مش بيحل على 191.218.161.133 (حالياً: $RESOLVED_APP)"
    echo "   انتظر انتشار الـ DNS وشغّل السكريبت تاني."
    exit 1
fi

echo "✅ DNS منتشر بشكل صحيح"

echo ""
echo "=== [2/5] طلب SSL certificates من Let's Encrypt ==="

# وقف nginx مؤقتاً عشان certbot يستخدم port 80
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml stop nginx
echo "nginx متوقف مؤقتاً..."

# طلب شهادة للموقع الرئيسي
sudo /snap/bin/certbot certonly --standalone \
    -d "$DOMAIN" \
    -d "www.$DOMAIN" \
    --agree-tos \
    --non-interactive \
    -m "$EMAIL" \
    --cert-name "$DOMAIN"

# طلب شهادة للتطبيق
sudo /snap/bin/certbot certonly --standalone \
    -d "$APP_DOMAIN" \
    --agree-tos \
    --non-interactive \
    -m "$EMAIL" \
    --cert-name "$APP_DOMAIN"

echo "✅ الشهادات اتعملت"

echo ""
echo "=== [3/5] تحديث .env.prod ==="
sed -i "s|PUBLIC_SITE_URL=.*|PUBLIC_SITE_URL=https://$DOMAIN|" backend/.env.prod
sed -i "s|CORS_ORIGINS=.*|CORS_ORIGINS=https://$DOMAIN,https://www.$DOMAIN,https://$APP_DOMAIN|" backend/.env.prod
echo "✅ .env.prod اتحدث"

echo ""
echo "=== [4/5] تشغيل النسخة الجديدة بالدومين ==="
docker compose -f docker-compose.prod.yml -f docker-compose.prod.domain.yml up -d --remove-orphans
echo "✅ containers شغالة"

echo ""
echo "=== [5/5] التحقق من الصحة ==="
sleep 5
curl -fsS "https://$DOMAIN" -o /dev/null -w "elkheima.com: HTTP %{http_code}\n" || echo "⚠️ elkheima.com مش راضي"
curl -fsS "https://$APP_DOMAIN/health" -o /dev/null -w "app.elkheima.com/health: HTTP %{http_code}\n" || echo "⚠️ app.elkheima.com مش راضي"

echo ""
echo "✅✅✅ تم التحويل لـ elkheima.com بنجاح!"
echo ""
echo "الروابط الجديدة:"
echo "  🌐 الموقع:     https://$DOMAIN"
echo "  👨‍💼 التطبيق:  https://$APP_DOMAIN"
