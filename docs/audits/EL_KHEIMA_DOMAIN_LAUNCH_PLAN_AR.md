# خطة الإطلاق النهائية الشاملة — الخيمة بيتش ريزورت
# elkheima.com — من IP إلى دومين كامل

> **تاريخ الإنشاء:** 2026-07-29  
> **الحالة الحالية للـ VPS:** شغّال على `191.218.161.133` بـ TLS قصير العمر — **ينتهي 2 أغسطس 2026 (3 أيام!)**  
> **الدومين المؤكد:** `elkheima.com` — مسجّل في Hostinger، DNS فاضي تمامًا الآن  
> **الهدف:** تشغيل `elkheima.com` + `app.elkheima.com` بـ TLS حقيقي دائم، مع commit للكود المحلي الجاهز

---

## 🚨 تحذير عاجل — TLS ينتهي في 3 أيام

شهادة `191.218.161.133` تنتهي **2026-08-02 09:59 UTC**.
لو ما اتعمل تحويل للدومين قبلها → الموقع هيطلع "Not Secure" أو يتوقف.
الأولوية رقم 1 هي تفعيل DNS الآن.

---

## الوضع الحالي الكامل

### ما شغّال على الـ VPS
| الخدمة | الحالة | الرابط |
|---|---|---|
| Staff App (el-kheima) | ✅ Up 45h healthy | `https://191.218.161.133` (port 443) |
| Marketing Site | ✅ Up 43h | `https://191.218.161.133:8443` |
| Backend API | ✅ Up 42h healthy | داخلي فقط |
| PostgreSQL | ✅ Up 2d healthy | `127.0.0.1:5436` فقط |
| Redis | ✅ Up 2d healthy | `127.0.0.1:6381` فقط |
| Celery Worker | ✅ Up 2d healthy | داخلي |
| Celery Beat | ✅ Up 2d healthy | داخلي |
| Nginx Edge | ✅ Up 2d | 80, 443, 8443 |

### الشهادات الموجودة
| الشهادة | انتهاء | الحالة |
|---|---|---|
| `191.218.161.133` | 2026-08-02 | ⚠️ **3 أيام فقط** |
| `srv1856853.hstgr.cloud` | 2026-10-24 | ✅ 87 يوم |

### الدومين
- `elkheima.com` → مسجّل في Hostinger كـ External Domain
- DNS records: **فاضية تمامًا — لا A records**
- `docker-compose.prod.domain.yml` → موجود محلياً فقط، **غير مرفوع**
- `deploy/nginx/edge-domain.conf` → موجود محلياً فقط، **غير مرفوع**
- `scripts/switch-to-domain.sh` → موجود محلياً فقط، **غير مرفوع**

### الكود المحلي غير المرفوع
- **42 ملف معدّل + 5 ملفات جديدة** جاهزة للـ commit
- تشمل: 9 bugfixes حرجة، migration PII، ملفات الدومين

---

## 📋 خطة التنفيذ — بالترتيب الإلزامي

### المرحلة 0 — Commit الكود المحلي (محلي، فوري)

```bash
cd /home/wego/projects/resort-os

# 1. تأكد من الحالة
git status --short | head -50
git diff --stat HEAD | tail -5

# 2. تشغيل الاختبارات
cd backend
source .venv/bin/activate
pytest tests/ -x -q --timeout=60 2>&1 | tail -20
cd ..

# 3. Commit
git add -A
git commit -m "fix(security+finance+perf+domain): branch isolation ×8 modules, \
payment race locks (timeshare+leasing), HR payroll cap, dining integrity error, \
leasing tasks partial/overdue, maintenance consume_stock, N+1 fixes ×3, \
HR permission tightening, hub PII encryption migration, domain nginx+compose files"

# 4. Push
git push origin main
```

**ملاحظة مهمة:** ملفات `edge-domain.conf` و`docker-compose.prod.domain.yml` و`switch-to-domain.sh` موجودة في الـ staging محلياً — الـ commit ده هيرفعهم.

---

### المرحلة 1 — إضافة DNS Records في Hostinger

**اذهب إلى:** Hostinger → Domains → elkheima.com → Manage DNS

أضف هذه الـ records بالترتيب:

| Type | Name | Value | TTL |
|---|---|---|---|
| A | `@` | `191.218.161.133` | **300** |
| A | `www` | `191.218.161.133` | **300** |
| A | `app` | `191.218.161.133` | **300** |
| CNAME | `_dmarc` | (اتركه فاضي الآن) | — |

> **لماذا TTL=300؟** عشان لو في مشكلة تقدر تغيّر بسرعة بدل ما تنتظر 14400 ثانية (4 ساعات).

**التحقق من الانتشار (من جهازك المحلي):**
```bash
# انتظر 2-10 دقائق ثم:
dig elkheima.com A @1.1.1.1 +short
dig www.elkheima.com A @1.1.1.1 +short
dig app.elkheima.com A @1.1.1.1 +short
# النتيجة المطلوبة من الثلاثة: 191.218.161.133
```

---

### المرحلة 2 — Deploy الكود الجديد على الـ VPS

بعد ما الـ push خلص في المرحلة 0:

```bash
ssh resort-os-vps "cd /opt/resort-os && bash scripts/deploy.sh"
```

ده هيعمل:
- ✅ Backup قاعدة البيانات
- ✅ git pull fast-forward
- ✅ docker compose build
- ✅ alembic upgrade head (migration PII الجديد)
- ✅ docker compose up -d
- ✅ health check

**التحقق بعد الـ deploy:**
```bash
ssh resort-os-vps "
  docker ps --format 'table {{.Names}}\t{{.Status}}'
  curl -sk https://191.218.161.133/health | python3 -m json.tool
  docker exec resort-os-prod-backend-1 alembic current
"
```

النتيجة المطلوبة لـ alembic: `88d1c505a9dc (head)`

---

### المرحلة 3 — طلب TLS للدومين وتشغيل switch-to-domain.sh

**شرط:** DNS انتشر وكل الـ 3 records تحل على `191.218.161.133`

```bash
ssh resort-os-vps "cd /opt/resort-os && bash scripts/switch-to-domain.sh"
```

السكريبت ده هيعمل تلقائياً:
1. يتحقق من انتشار DNS لـ `elkheima.com` و`app.elkheima.com`
2. يوقف nginx مؤقتًا
3. يطلب شهادة Let's Encrypt لـ `elkheima.com` و`www.elkheima.com`
4. يطلب شهادة Let's Encrypt لـ `app.elkheima.com`
5. يحدث `.env.prod` تلقائيًا: `PUBLIC_SITE_URL=https://elkheima.com`
6. يشغّل الـ compose بـ `docker-compose.prod.domain.yml`
7. يتحقق من الصحة

**لو فشل السكريبت في إصدار الشهادة:**
```bash
# راجع السبب
ssh resort-os-vps "sudo cat /var/log/letsencrypt/letsencrypt.log | tail -30"
# أكثر أسباب الفشل: DNS لسه مش انتشر، أو rate limit
```

---

### المرحلة 4 — التحقق النهائي بعد التحويل

```bash
# من جهازك المحلي — اختبر كل الروابط:
curl -I https://elkheima.com
curl -I https://www.elkheima.com
curl -I https://app.elkheima.com/health

# التحقق من الشهادات:
echo | openssl s_client -connect elkheima.com:443 -servername elkheima.com 2>/dev/null | openssl x509 -noout -subject -dates
echo | openssl s_client -connect app.elkheima.com:443 -servername app.elkheima.com 2>/dev/null | openssl x509 -noout -subject -dates

# التحقق من الـ VPS:
ssh resort-os-vps "
  docker ps --format 'table {{.Names}}\t{{.Status}}'
  curl -fsS https://elkheima.com -o /dev/null -w 'elkheima.com: %{http_code}\n'
  curl -fsS https://app.elkheima.com/health -o /dev/null -w 'app.elkheima.com: %{http_code}\n'
"
```

**النتائج المطلوبة:**
- `elkheima.com` → HTTP 200، شهادة صادرة لـ `elkheima.com` من Let's Encrypt
- `app.elkheima.com` → HTTP 200، health check OK
- كل الـ containers: `Up (healthy)`

---

### المرحلة 5 — تحديث الـ Renewal Hooks

بعد التحويل للدومين، الـ IP certificate مش هيتجدد تلقائيًا. تأكد:

```bash
ssh resort-os-vps "
  # شوف الـ renewal configs الموجودة
  sudo ls /etc/letsencrypt/renewal/

  # تأكد إن certbot timer شغّال
  sudo systemctl status certbot.timer 2>/dev/null || sudo systemctl status snap.certbot.renew.timer
  
  # اختبر التجديد التجريبي
  sudo certbot renew --dry-run
"
```

---

## 🗺️ الخريطة الكاملة بعد التحويل

```
المستخدم العام (ضيف/زائر):
  elkheima.com      → marketing_site container → الموقع التسويقي + QR + منيو
  www.elkheima.com  → نفس marketing_site

الموظفون:
  app.elkheima.com  → el_kheima container → staff POS/KDS/back office

API:
  app.elkheima.com/api/v1/* → backend container (داخلي، مش مكشوف للعامة)
  elkheima.com/api/v1/*    → نفس backend (للتطبيق العام)
```

---

## ⚙️ التغييرات التي يعملها switch-to-domain.sh في .env.prod

```diff
- PUBLIC_SITE_URL=https://191.218.161.133:8443
+ PUBLIC_SITE_URL=https://elkheima.com

- CORS_ORIGINS=https://191.218.161.133,https://191.218.161.133:8443
+ CORS_ORIGINS=https://elkheima.com,https://www.elkheima.com,https://app.elkheima.com
```

**بعد التحويل يدوياً تحتاج تتحقق وتحدث:**
```bash
ssh resort-os-vps "grep -E 'PUBLIC_SITE_URL|CORS_ORIGINS|CHAT_PUBLIC_HOST' /opt/resort-os/backend/.env.prod"
```

وتحديث `CHAT_PUBLIC_HOST_BRANCH_MAP` من:
```
CHAT_PUBLIC_HOST_BRANCH_MAP={"191.218.161.133": 1}
```
إلى:
```
CHAT_PUBLIC_HOST_BRANCH_MAP={"elkheima.com": 1, "www.elkheima.com": 1}
```

---

## 📋 Checklist التنفيذ — تشيك كل خطوة

### قبل بداية أي خطوة
- [ ] قرأت هذا الملف كاملاً
- [ ] التحقق من حالة الـ VPS: `ssh resort-os-vps "docker ps"`

### المرحلة 0 — Commit
- [ ] `git status` — 42+ ملف modified
- [ ] `pytest tests/ -x -q` — كل الاختبارات ناجحة (لا failures)
- [ ] `git add -A && git commit -m "..."` — تم
- [ ] `git push origin main` — تم بدون rejection

### المرحلة 1 — DNS
- [ ] A record لـ `@` → `191.218.161.133` أضيف في Hostinger
- [ ] A record لـ `www` → `191.218.161.133` أضيف
- [ ] A record لـ `app` → `191.218.161.133` أضيف
- [ ] `dig elkheima.com A @1.1.1.1` → يرجع `191.218.161.133`
- [ ] `dig app.elkheima.com A @1.1.1.1` → يرجع `191.218.161.133`

### المرحلة 2 — Deploy
- [ ] `bash scripts/deploy.sh` على الـ VPS نجح
- [ ] `alembic current` → `88d1c505a9dc (head)`
- [ ] `curl -sk https://191.218.161.133/health` → `{"status": "ok"}`

### المرحلة 3 — Switch to Domain
- [ ] DNS انتشر (المرحلة 1 مكتملة)
- [ ] `bash scripts/switch-to-domain.sh` نجح
- [ ] شهادة `elkheima.com` صدرت من Let's Encrypt
- [ ] شهادة `app.elkheima.com` صدرت من Let's Encrypt
- [ ] Containers مشغّلة بـ `docker-compose.prod.domain.yml`

### المرحلة 4 — التحقق
- [ ] `https://elkheima.com` → يفتح الموقع (HTTP 200)
- [ ] `https://www.elkheima.com` → يفتح (HTTP 200)
- [ ] `https://app.elkheima.com` → يفتح staff app
- [ ] `https://app.elkheima.com/health` → `{"status": "ok"}`
- [ ] الشهادات صادرة لـ domain (مش IP)
- [ ] HSTS header موجود

### المرحلة 5 — Post-Switch
- [ ] `CHAT_PUBLIC_HOST_BRANCH_MAP` اتحدث في `.env.prod`
- [ ] `certbot renew --dry-run` نجح
- [ ] الـ renewal timer شغّال: `sudo systemctl is-active snap.certbot.renew.timer`

---

## 🔄 خطة التراجع

لو `switch-to-domain.sh` فشل أو في مشكلة في الدومين:

```bash
# رجّع للـ IP-TLS السابق
ssh resort-os-vps "
  cd /opt/resort-os
  docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml up -d --remove-orphans
"
# الموقع يرجع على https://191.218.161.133 و https://191.218.161.133:8443
```

> **ملاحظة:** الـ IP certificate ينتهي 2 أغسطس. لو تراجعت وما شغّلتش الدومين قبلها، لازم تجدد الشهادة يدوياً:
> ```bash
> ssh resort-os-vps "sudo certbot renew --cert-name 191.218.161.133 --force-renewal"
> ```

---

## 🔮 ما بعد الإطلاق — المهام التالية

### عاجل (الأسبوع الأول)
1. **إنشاء Super Admin حقيقي** — تفاعلياً عبر الـ Staff App، لا وكيل يشارك في الأسرار
2. **إنشاء أول فرع** — `El Kheima Beach` + ربطه بالـ Host
3. **تحديث CHAT_PUBLIC_HOST_BRANCH_MAP** في `.env.prod` بعد التحويل

### قريب (خلال أسبوعين)
4. **CX-02C Frontend** — auth store، branch selector، إزالة `branch_id ?? 1`
5. **Gate 5 Production Data** — master data من المالك، dry-run/import/reconcile
6. **UAT على الدومين الحقيقي** — من أجهزة حقيقية، كل role وكل فرع

### متوسط (قبل soft launch)
7. **تشفير PII القديم** في `hub_online_bookings` — migration منفصل بعد approval
8. **اختبار Race Condition** على Postgres حقيقي:
   ```bash
   DINING_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://postgres:<pass>@191.218.161.133:5436/resort_os \
     pytest backend/tests/test_timeshare_leasing_concurrency.py -v
   ```
9. **تفعيل Monitoring** — uptime check على `https://elkheima.com` و`https://app.elkheima.com/health`
10. **TTL ترفعه لـ 3600** بعد استقرار الدومين أسبوع

### مؤجل (يحتاج بيانات المالك)
11. اعتماد بيانات الاتصال الحقيقية (هاتف/بريد معتمد)
12. استيراد master data: غرف، موظفين، أسعار، منيو
13. اعتماد محاسب للضرائب وopening balances
14. Go/No-Go لإطلاق الـ business operations

---

## 📞 بيانات التواصل والمراجع

| المورد | التفاصيل |
|---|---|
| VPS IP | `191.218.161.133` |
| VPS SSH | `ssh resort-os-vps` أو `ssh -i ~/.ssh/id_ed25519 resortos@191.218.161.133` |
| Hostinger DNS | hPanel → Domains → elkheima.com → Manage DNS |
| Staff App (IP) | `https://191.218.161.133` |
| Marketing (IP) | `https://191.218.161.133:8443` |
| Staff App (Domain) | `https://app.elkheima.com` (بعد التحويل) |
| Marketing (Domain) | `https://elkheima.com` (بعد التحويل) |
| Health Check | `/health` على backend |
| Project Dir VPS | `/opt/resort-os` |
| Marketing Dir VPS | `/opt/elkheima-marketing-website` |
| Compose Command | `docker compose -f docker-compose.prod.yml -f docker-compose.prod.domain.yml` |

---

## 🐛 الـ Bugfixes المضمنة في الـ Commit القادم

| الكود | الوصف | الأثر |
|---|---|---|
| B-01 | Branch Isolation ×8 modules | أمني حرج — عزل الفروع |
| B-02 | Finance folio/branch_id من path | مالي حرج |
| B-03 | Finance void_payment مسار خاطئ | مالي حرج |
| B-04 | Timeshare race condition | مالي حرج — أقساط مزدوجة |
| B-05 | Leasing race condition | مالي حرج |
| B-06 | Maintenance add_part_to_wo 400 دائمًا | وظيفي |
| B-07 | Dining create_order 500 عند تصادم | وظيفي |
| B-08 | Leasing tasks partial/overdue | مالي متوسط |
| B-09 | HR صافي راتب سالب | مالي متوسط |
| PERF-01 | N+1 في dining/leasing/hr | أداء |
| MIG-01 | PII encryption لـ hub_online_bookings | أمني |

---

*آخر تحديث: 2026-07-29 — Kiro بعد فحص مباشر للـ VPS والدومين والكود المحلي*
