# AGENT_VPS_REFERENCE — Resort OS VPS Operations Guide

> **الغرض:** مرجع شامل للوكيل (Agent/AI) يعمل على هذا المشروع.
> يحتوي على كل ما يلزم لفهم البيئة والعمل عليها أو نقلها لـ VPS جديد.
>
> **آخر تحديث:** 2026-07-25
> **الحالة:** Production — شغّال

---

## 1. معلومات الـ VPS الحالي

| البند | القيمة |
|---|---|
| **IP** | `187.124.170.249` |
| **نظام التشغيل** | Ubuntu 24.04.4 LTS (Noble Numbat) |
| **CPU** | 2 cores |
| **RAM** | 7.8 GB (1.8 مستخدم، 6 متاح) |
| **Disk** | 96 GB (23 مستخدم — 24%) |
| **Docker** | 29.6.0 |
| **Docker Compose** | v5.2.0 |
| **Git** | 2.43.0 |
| **Certbot** | 5.7.0 |

### SSH
```bash
ssh root@187.124.170.249
# أو مع key:
ssh -i ~/.ssh/resort-os-key root@187.124.170.249
```

---

## 2. هيكل المشروع على السيرفر

```
/opt/wegosharm/
├── resort-os/                  ← المشروع النشط الحالي
│   ├── backend/
│   │   ├── .env.prod           ← متغيرات البيئة (أسرار — لا تُعرض)
│   │   ├── Dockerfile
│   │   └── app/
│   ├── frontend/
│   ├── docker-compose.prod.yml
│   ├── docker-compose.prod.ip-tls.yml   ← الـ override النشط (HTTPS)
│   ├── docker-compose.prod.ip-only.yml  ← بديل HTTP فقط
│   ├── deploy/
│   │   ├── nginx/
│   │   │   ├── edge.conf
│   │   │   ├── edge-ip-only.conf
│   │   │   └── edge-ip-tls.conf
│   │   ├── systemd/
│   │   │   ├── resort-os-backup.service
│   │   │   ├── resort-os-backup.timer
│   │   │   ├── resort-os-certbot-renew.service
│   │   │   └── resort-os-certbot-renew.timer
│   │   └── certbot/
│   │       └── reload-resort-os-nginx.sh
│   ├── scripts/
│   │   ├── deploy.sh           ← السكريبت الرئيسي للـ deploy
│   │   ├── backup_db.sh
│   │   └── restore_db.sh
│   └── backups/                ← PostgreSQL dumps (آخر 14 يوم)
│
├── resort-os.old.20260708_091931/   ← backup قديم (يمكن حذفه)
└── resort-os.old.20260710_193246/   ← backup قديم (يمكن حذفه)
```

---

## 3. Docker Project

**اسم الـ project:** `resort-os`

### الـ Containers (8 containers)

| Container | Image | Port | الوظيفة |
|---|---|---|---|
| `resort-os-backend-1` | `resort-os-backend` | `127.0.0.1:8005` | FastAPI backend |
| `resort-os-el_kheima-1` | `resort-os-el_kheima` | internal | Staff app (nginx static) |
| `resort-os-public_site-1` | `resort-os-public_site` | internal | Guest public site (nginx static) |
| `resort-os-celery_worker-1` | `resort-os-celery_worker` | — | Background tasks |
| `resort-os-celery_beat-1` | `resort-os-celery_beat` | — | Task scheduler |
| `resort-os-nginx-1` | `nginx:1.27-alpine` | 80, 443, 8081, 8443 | Edge reverse proxy |
| `resort-os-db_postgres-1` | `postgres:16` | `127.0.0.1:5436` | Database |
| `resort-os-redis_cache-1` | `redis:7-alpine` | `127.0.0.1:6381` | Cache + Celery broker |

### الـ Volumes

| Volume | المحتوى |
|---|---|
| `resort-os_resort_pgdata` | PostgreSQL data |
| `resort-os_resort_redisdata` | Redis data |
| `resort-os_certbot_certs` | TLS certificates |
| `resort-os_certbot_www` | ACME challenge files |

---

## 4. الـ URLs

| الوصف | الرابط |
|---|---|
| Staff App (موظفين) | `https://187.124.170.249/` |
| Public Site (ضيوف) | `https://187.124.170.249:8443/` |
| Health Check | `https://187.124.170.249/health` |
| HTTP Redirect | `http://187.124.170.249:8081/` → يعيد التوجيه لـ 8443 |
| API (داخلي) | `http://127.0.0.1:8005/api/v1/` |

---

## 5. الأوامر اليومية

### فحص الحالة
```bash
cd /opt/wegosharm/resort-os

# حالة الـ containers
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml ps

# health check
curl -fsS https://187.124.170.249/health -k | python3 -m json.tool

# أو مباشرة من داخل الـ backend
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml \
  exec -T backend curl -fsS http://127.0.0.1:8005/health
```

### Deploy تحديث (الطريقة الرسمية)
```bash
cd /opt/wegosharm/resort-os
bash scripts/deploy.sh
```
السكريبت يعمل تلقائياً:
1. PostgreSQL backup
2. `git pull --ff-only origin main`
3. `docker compose build`
4. `alembic upgrade head`
5. `docker compose up -d`
6. Health check

### Deploy يدوي (للـ backend فقط)
```bash
cd /opt/wegosharm/resort-os
git pull --ff-only origin main
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml build backend
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml up -d --no-deps backend
```

### Deploy يدوي (للـ frontend فقط)
```bash
cd /opt/wegosharm/resort-os
git pull --ff-only origin main
# el-kheima (staff app)
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml build el_kheima
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml up -d --no-deps el_kheima
# أو public_site
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml build public_site
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml up -d --no-deps public_site
```

### لوجات
```bash
cd /opt/wegosharm/resort-os
COMPOSE="docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml"

$COMPOSE logs backend --tail=100 -f
$COMPOSE logs celery_worker --tail=50 -f
$COMPOSE logs nginx --tail=50
```

---

## 6. TLS Certificate

- **نوع:** IP certificate (Let's Encrypt) — مش domain
- **IP المسجّل:** `187.124.170.249`
- **المسار:** `/etc/letsencrypt/live/187.124.170.249/`
- **التجديد:** تلقائي عبر systemd timer مرتين يومياً (03:20 و 15:20 UTC)
- **Certbot hook:** `deploy/certbot/reload-resort-os-nginx.sh`

### فحص الشهادة
```bash
certbot certificates
openssl s_client -connect 187.124.170.249:443 2>/dev/null | openssl x509 -noout -dates
```

---

## 7. Database

- **نوع:** PostgreSQL 16
- **اسم الـ DB:** `resort_os`
- **User:** `postgres`
- **Port (خارجي على host):** `127.0.0.1:5436`
- **Port (داخل Docker network):** `5432`
- **Host (داخل Compose):** `db_postgres`

### اتصال مباشر
```bash
docker compose -f /opt/wegosharm/resort-os/docker-compose.prod.yml exec db_postgres \
  psql -U postgres -d resort_os
```

### Migrations
```bash
cd /opt/wegosharm/resort-os
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml \
  run --rm backend alembic upgrade head

# فحص الحالة
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml \
  run --rm backend alembic check
```

---

## 8. Backup & Restore

### Backup يدوي
```bash
cd /opt/wegosharm/resort-os
ENV_FILE=backend/.env.prod bash scripts/backup_db.sh
# الـ dump يُحفظ في /opt/wegosharm/resort-os/backups/
```

### Restore
```bash
cd /opt/wegosharm/resort-os
bash scripts/restore_db.sh backups/resort_os_YYYYMMDD_HHMMSS.dump
```

### Automatic Backup
- **جدول:** كل يوم (systemd timer)
- **مدة الاحتفاظ:** 14 يوم
- **مكان الحفظ:** `/opt/wegosharm/resort-os/backups/`

---

## 9. GitHub Repository

| البند | القيمة |
|---|---|
| **Repo** | `git@github.com:wego2388/Resort-OS.git` |
| **Branch النشط** | `main` |
| **Clone** | `git clone git@github.com:wego2388/Resort-OS.git resort-os` |

### قواعد Git في هذا المشروع
- لا `git add .` — stage الملفات بالاسم صراحةً
- لا commit إلا بإذن صريح من Mohamed
- لا push إلا بإذن صريح من Mohamed
- الـ deploy دائماً `--ff-only` (لا merge conflicts)

---

## 10. نقل المشروع لـ VPS جديد

### الخطوات الكاملة

#### أ. على الـ VPS الجديد — تجهيز البيئة
```bash
# تثبيت Docker
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# تثبيت Certbot
apt install -y certbot

# إنشاء مجلد
mkdir -p /opt/wegosharm
cd /opt/wegosharm

# استنساخ المشروع
git clone git@github.com:wego2388/Resort-OS.git resort-os
cd resort-os
```

#### ب. نسخ الأسرار من السيرفر القديم
```bash
# على السيرفر القديم — نسخ .env.prod
scp root@187.124.170.249:/opt/wegosharm/resort-os/backend/.env.prod \
    root@NEW_IP:/opt/wegosharm/resort-os/backend/.env.prod

# تحديث الـ IP الجديد في .env.prod
# غيّر: CORS_ORIGINS و PUBLIC_SITE_URL و أي URL يحتوي IP القديم
```

#### ج. نقل قاعدة البيانات
```bash
# على السيرفر القديم — عمل backup
cd /opt/wegosharm/resort-os
ENV_FILE=backend/.env.prod bash scripts/backup_db.sh

# نقل الـ dump للسيرفر الجديد
scp backups/resort_os_LATEST.dump root@NEW_IP:/opt/wegosharm/resort-os/backups/
```

#### د. على الـ VPS الجديد — تثبيت شهادة TLS
```bash
# ⚠️ ملاحظة: شهادات IP من Let's Encrypt تحتاج ACME challenge HTTP
# شغّل أولاً بدون TLS
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-only.yml up -d nginx

# اطلب الشهادة
certbot certonly --webroot \
  -w /var/lib/letsencrypt \
  --domain NEW_IP \
  --email theagaty@gmail.com \
  --agree-tos --non-interactive

# أو استخدم standalone
certbot certonly --standalone -d NEW_IP --email theagaty@gmail.com --agree-tos
```

#### هـ. تشغيل الـ stack الكامل
```bash
cd /opt/wegosharm/resort-os

# أول مرة — build كامل + migrations + تشغيل
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml up -d --build

# restore قاعدة البيانات
bash scripts/restore_db.sh backups/resort_os_LATEST.dump
```

#### و. تثبيت الـ systemd timers
```bash
cd /opt/wegosharm/resort-os

# نسخ service files
cp deploy/systemd/resort-os-backup.service /etc/systemd/system/
cp deploy/systemd/resort-os-backup.timer /etc/systemd/system/
cp deploy/systemd/resort-os-certbot-renew.service /etc/systemd/system/
cp deploy/systemd/resort-os-certbot-renew.timer /etc/systemd/system/

# تفعيل
systemctl daemon-reload
systemctl enable --now resort-os-backup.timer
systemctl enable --now resort-os-certbot-renew.timer

# تحقق
systemctl list-timers | grep resort
```

#### ز. تحديث الـ repo بالـ IP الجديد
```bash
# في ملف backend/.env.prod على السيرفر الجديد:
# CORS_ORIGINS=https://NEW_IP,https://NEW_IP:8443
# PUBLIC_SITE_URL=https://NEW_IP:8443
```

#### ح. تحديث nginx configs (إذا تغيّر الـ IP)
```bash
# في deploy/nginx/edge-ip-tls.conf
# غيّر server_name و ssl_certificate path لـ IP الجديد
```

---

## 11. متغيرات البيئة المهمة (مفاتيح فقط — بدون قيم)

يجب نسخها من السيرفر القديم أو إعادة إنشائها:

```
DATABASE_URL          # postgresql://postgres:PASS@db_postgres:5432/resort_os
SECRET_KEY            # 32+ chars random — python -c "import secrets; print(secrets.token_urlsafe(48))"
FIELD_ENCRYPTION_KEY  # Fernet key — python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SURVEY_TOKEN_SECRET   # random string
REDIS_URL             # redis://redis_cache:6379/0
CELERY_BROKER_URL     # redis://redis_cache:6379/1
RESORT_NAME           # اسم المنتجع
TIMEZONE              # Africa/Cairo
CORS_ORIGINS          # https://NEW_IP,https://NEW_IP:8443
PUBLIC_SITE_URL       # https://NEW_IP:8443
WHATSAPP_ACCESS_TOKEN # من Meta Business
WHATSAPP_PHONE_ID     # من Meta Business
PAYMOB_API_KEY        # من Paymob dashboard
ETA_CLIENT_ID         # من هيئة الضرائب
ETA_CLIENT_SECRET     # من هيئة الضرائب
```

---

## 12. فحص سريع بعد أي deploy

```bash
# 1. health check
curl -fsS https://IP/health -k | python3 -m json.tool

# 2. حالة الـ containers
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml ps

# 3. آخر لوجات backend
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml \
  logs backend --tail=50

# ✅ المتوقع:
# status: ok
# database: ok
# redis: ok
# كل الـ containers: healthy
```

---

## 13. ملاحظات مهمة للوكيل

- **لا تعدّل** `docker-compose.yml` (ده للـ local dev فقط، غير `docker-compose.prod.yml`)
- **الـ project name** في Docker هو `resort-os` — مهم لعمليات الـ volumes
- **الـ VPS الحالي** يستخدم IP certificate (مش domain) — تجديدها يدوم ~6 أيام فقط
- **Alembic** لازم يشتغل قبل restart الـ backend في أي deploy يحتوي migrations
- **البيانات الحساسة** في `backend/.env.prod` — موجودة على السيرفر فقط، مش في الـ repo
- **الـ backup** يحصل تلقائياً يومياً، لكن قبل أي تغيير كبير اعمل backup يدوي
- **`deploy.sh`** هو الطريقة الرسمية والأأمن للـ deploy — يعمل backup قبل أي تغيير
