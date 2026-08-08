# Handoff — MKT-SS-01: Smart Beach Service Page
**Date:** 2026-08-06
**Agent:** Kiro
**Commit:** `bc48f09` — Marketing website (`main`)
**Status:** Ready for production deploy

---

## ما اتعمل

صفحة تسويقية مستقلة `/smart-service` لعرض فيتشر الـ QR ordering بأعلى
مستوى من التفاعل والجودة البصرية.

### الملفات الجديدة
```
src/apps/public/SmartService.vue          ← الصفحة الكاملة
src/styles/smart-service-1.css            ← Hero + base styles
src/styles/smart-service-2.css            ← Phone mockup + steps
src/styles/smart-service-3.css            ← Stats + How + Langs + CTA + keyframes
src/components/sections/QrOrderFeature.vue ← Component مرجعي (للاستخدام في sections)
src/components/sections/QrOrderFeature.md  ← توثيق QrOrderFeature
scripts/capture/capture-qr-screens.mjs    ← سكريبت تصوير screenshots (اختياري)
```

### الملفات المعدّلة
```
src/router/routes/public.routes.ts        ← إضافة route /smart-service
src/apps/public/Home.vue                  ← Teaser card بعد Restaurant section
src/i18n/locales/en.json                  ← smartService + qrFeature keys
src/i18n/locales/ar.json                  ← نفس الـ keys بالعربي
src/i18n/locales/ru.json                  ← نفس الـ keys بالروسي
src/i18n/locales/it.json                  ← نفس الـ keys بالإيطالي
```

### محتوى الصفحة (من فوق لتحت)
1. **Hero** — خلفية parallax + staggered 3-word headline (اجلس/امسح/اطلب)
2. **Demo تفاعلي** — iPhone mockup بـ 4 شاشات حية + steps timeline مع auto-play
3. **Stats** — counters تتحرك لما تظهر في الشاشة
4. **How it works** — 3 cards مع animated bottom line
5. **Languages showcase** — 4 mini phones بـ AR/EN/RU/IT
6. **Final CTA** — زر demo + زر حجز

---

## Validation ✅
```
npm run validate  →  public-truth ✓ + type-check ✓ + build ✓
git commit        →  bc48f09 (13 files, 3964 insertions)
```

---

## خطوات النشر على الـ VPS

هذا marketing-only deploy — **لا migration، لا backend تغيير**.

### A. من المحلي — إنشاء أرشيف
```bash
cd /home/wego/projects/elkheima-marketing-website
COMMIT=$(git rev-parse HEAD)
# bc48f09...

git archive --format=tar.gz --prefix=elkheima-marketing-${COMMIT}/ \
  HEAD -o /tmp/elkheima-marketing-${COMMIT}.tar.gz

sha256sum /tmp/elkheima-marketing-${COMMIT}.tar.gz
# احتفظ بالـ checksum
```

### B. رفع الأرشيف للـ VPS
```bash
scp /tmp/elkheima-marketing-${COMMIT}.tar.gz \
  resort-os-vps:/var/backups/resort-os/marketing-source-releases/

# تحقق الـ checksum على الـ VPS
ssh resort-os-vps "sha256sum /var/backups/resort-os/marketing-source-releases/elkheima-marketing-${COMMIT}.tar.gz"
# يطابق الـ local checksum بالضبط
```

### C. على الـ VPS — إنشاء release جديد
```bash
ssh resort-os-vps

COMMIT=bc48f09  # أو القيمة الكاملة من git rev-parse
RELEASE_DIR="/opt/elkheima-marketing-releases/${COMMIT}"

sudo mkdir -p "$RELEASE_DIR"
sudo tar -xzf /var/backups/resort-os/marketing-source-releases/elkheima-marketing-${COMMIT}.tar.gz \
  --strip-components=1 -C "$RELEASE_DIR"

# تحقق من وجود الملفات الجديدة
ls "$RELEASE_DIR/src/apps/public/SmartService.vue"
ls "$RELEASE_DIR/src/styles/smart-service-1.css"
```

### D. Tag rollback image للـ marketing_site الحالي
```bash
CURRENT_IMG=$(docker inspect resort-os-prod-marketing_site-1 \
  --format '{{.Image}}')
docker tag "$CURRENT_IMG" \
  resort-os-rollback/marketing-site:pre-${COMMIT}

# سجّل في rollback manifest
echo "marketing-site: $CURRENT_IMG" >> \
  /var/backups/resort-os/source-releases/${COMMIT}-rollback-images.txt
```

### E. Update symlink وبناء الصورة
```bash
# الـ RESORT_ACTIVE_RELEASE = المسار الحالي لـ resort-os
RESORT_ACTIVE_RELEASE=$(docker inspect resort-os-prod-backend-1 \
  --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')

cd "$RESORT_ACTIVE_RELEASE"

# حدّث MARKETING_SITE_CONTEXT ليشير للـ release الجديد
sudo ln -sfn "$RELEASE_DIR" /opt/elkheima-marketing-current

# تحقق
readlink /opt/elkheima-marketing-current
# /opt/elkheima-marketing-releases/bc48f09

# اشتق DB_PASSWORD (بدون طباعته)
DATABASE_URL_VALUE=$(sed -n 's/^DATABASE_URL=//p' backend/.env.prod | head -1 | cut -d= -f2-)
DB_PASSWORD=$(RESORT_DATABASE_URL="$DATABASE_URL_VALUE" python3 -c '
import os
from urllib.parse import urlparse
url = os.environ["RESORT_DATABASE_URL"].replace("postgresql+psycopg://","postgresql://",1)
print(urlparse(url).password)
')
export DB_PASSWORD

RESORT_COMPOSE=(
  docker compose --env-file backend/.env.prod
  -f docker-compose.prod.yml
  -f docker-compose.prod.domain.yml
)

# بناء marketing_site فقط
"${RESORT_COMPOSE[@]}" build marketing_site

# استبدال
"${RESORT_COMPOSE[@]}" up -d --no-deps marketing_site
```

### F. Post-deploy checks
```bash
sleep 8
docker ps --filter "name=marketing" --format "{{.Names}}|{{.Status}}"
# يظهر: Up ... (healthy) أو Up ...

curl -fsSI https://elkheima.com/
curl -fsSI https://www.elkheima.com/
# HTTP/2 200

# تحقق من الصفحة الجديدة
curl -fsS https://elkheima.com/ar/smart-service | grep -o "Smart Beach Service" | head -1
# Smart Beach Service
```

### G. Smoke test بشري
- افتح `https://elkheima.com/ar/smart-service` على موبايل
- تأكد الـ hero animation شغالة
- تأكد الـ phone mockup بيتبدّل بين الشاشات
- افتح `https://elkheima.com/en/smart-service` — تأكد الإنجليزي
- تأكد الـ teaser ظاهر في الـ Home page

### H. Update symlink النهائي وسجّل
```bash
sudo ln -sfn "$RELEASE_DIR" /opt/elkheima-marketing-current
# (لو مش عملته بالفعل في step E)
```

---

## Rollback (لو حاجة وحشت)
```bash
# رجّع الصورة القديمة
docker tag resort-os-rollback/marketing-site:pre-${COMMIT} \
  resort-os-prod_marketing_site:latest

cd "$RESORT_ACTIVE_RELEASE"
"${RESORT_COMPOSE[@]}" up -d --no-deps marketing_site

# رجّع الـ symlink للـ release السابق
sudo ln -sfn /opt/elkheima-marketing-releases/79130a6 /opt/elkheima-marketing-current
```

---

## ملاحظات

- **لا migration** — marketing-only change، الـ backend مش محتاج يتلمس
- **لا backend restart** — بناء `marketing_site` container بس
- الـ warning على `public-pages` chunk كان موجود قبل هذا الـ commit — مش جديد
- `scripts/capture/capture-qr-screens.mjs` — سكريبت اختياري لتصوير screenshots حقيقية من `/s/demo`، يحتاج `npm install puppeteer --save-dev` أولاً ثم `node scripts/capture/capture-qr-screens.mjs`
