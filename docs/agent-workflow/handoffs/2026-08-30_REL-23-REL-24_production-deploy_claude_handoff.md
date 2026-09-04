# نشر REL-23 + REL-24 على الإنتاج — VPS الجديد (31.97.193.77)

## السياق

بعد الموافقة على REL-23 (C-01) وREL-24 (H-01→M-04) ودمجهم وpush، طلب Mohamed
البدء في الـ deploy الفعلي ("ابدأ الـ deploy"). تبيّن إن السيرفر الموثّق في
`DEPLOYMENT.md` (`191.218.161.133`) لم يعد الصحيح — Mohamed أرسل سكرين شوتات
تؤكد إن الـ DNS الحقيقي بقى موجّه لسيرفر جديد (`31.97.193.77`، alias
`resort-os-vps-new`)، مسبوقًا بتوثيق سابق (`reference_resort_os_vps.md`) بإنه
"مجهّز بالكامل، ناقصه بس DNS cutover + certbot". الـ deploy اتنفّذ بالكامل
على السيرفر ده باتباع `DEPLOYMENT.md` §5 حرفيًا، مع إضافة حقيقية غير موثّقة في
الـ runbook (إصدار شهادة TLS لأول مرة) اتكشفت أثناء التنفيذ.

**Commit المنشور**: `0e55ac038a8603d2fa4f24e5353a2c9a0288fb45` (REL-23 + REL-24
مجتمعين، فرع `codex/rel-15-auth-ops-readiness`).
**كان شغال قبل كده**: `2a6cb923f05a9b94d67a19268e38def4ec376084` (REL-22).

## التنفيذ (DEPLOYMENT.md §5، بالترتيب)

- **A. Local release gate**: كل الاختبارات + type-check + build محليًا أخضر.
- **B. Release artifact**: `git archive` من الـ commit، SHA-256 اتأكد مطابقته
  على السيرفر، استخراج لـ `/opt/resort-os-releases/<sha>/` (مجلد جديد، بدون
  الكتابة فوق أي حاجة)، `.env.prod` منسوخ بصلاحية `0600`،
  `validate_prod_env.py` عدّى.
- **C. Rollback point**: 7 صور Docker الحالية اتعلّمت `pre-<commit>` وسُجّلت
  IDs في `/var/backups/resort-os/source-releases/`. نسخة احتياطية حقيقية جديدة
  من قاعدة البيانات (`backup_db.sh`) اتعملها تحقق فعلي بـ`pg_restore --list`
  (1659 TOC entry).
- **D. Build + preflight**: `docker compose build --parallel backend el_kheima
  owner` نجح. الاستيراد (`python -c 'from app.main import app'`) رجع
  `El Kheima Beach` صح. `alembic heads` = head واحد (`6449668eb81a`).
  `alembic upgrade head` نجح — **اتأكد بالقراءة المباشرة من قاعدة البيانات**
  (`SELECT version_num FROM alembic_version`) مش بس بالاعتماد على exit code
  السكريبت (محاولة أولى بسكريبت مُركّب أعطت exit_code=0 مضلّل — الآوتبوت
  اتقطع قبل مرحلة الـ migration فعليًا، فاتعمل إعادة تشغيل بسيطة ومباشرة
  اتأكدت مباشرة من قاعدة البيانات).
- **E. Controlled replacement**: استبدال بالترتيب (backend → celery_worker +
  celery_beat → el_kheima + owner → nginx)، مع انتظار health check حقيقي بعد
  كل خطوة قبل الانتقال للتالية. كل container بقى `healthy`، `RestartCount=0`،
  وimage tag مطابق للـ commit الجديد.

## اكتشاف حقيقي أثناء التنفيذ: TLS مكانتش موجودة خالص على السيرفر ده

استبدال `nginx` (`--force-recreate`) كشف إن `/etc/letsencrypt/live/` مش موجود
خالص على هذا السيرفر — nginx كان بيدخل crash loop لأن ملف الشهادة
(`fullchain.pem`) مش موجود. هذا **مش تراجع سببه الـ deploy** — ده الفجوة
الوحيدة الباقية من إعداد السيرفر الجديد أصلاً (موثّقة سابقًا في الذاكرة:
"مجهّز بالكامل، ناقصه بس DNS cutover + certbot"). لحظة ما الـ DNS اتحوّل
لهذا السيرفر (سكرين شوت Mohamed الأخير)، ظهرت الفجوة دي فعليًا لأول مرة.

`DEPLOYMENT.md` §9 بيوثّق **التجديد** بس (`certbot renew`)، مش **الإصدار
الأول**. اتنفّذ الإصدار الأول بموافقة صريحة من Mohamed:

1. إيقاف `nginx` (كان أصلاً واقع، `docker stop` لتحرير بورت 80 فعليًا).
2. `certbot certonly --standalone -d elkheima.com -d www.elkheima.com
   -d app.elkheima.com -d owner.elkheima.com --agree-tos
   --register-unsafely-without-email --non-interactive` — نجح من أول محاولة
   (نجح، صالحة لغاية 2026-11-28). `--register-unsafely-without-email`
   مقصودة: مفيش قناة موثّقة لإرسال إيميل Mohamed الشخصي لخدمة طرف ثالث بدون
   إذن صريح لذلك تحديدًا، والتجديد التلقائي مش معتمد على إيميلات التنبيه أصلاً.
3. تشغيل `nginx` تاني — نجح، الشهادة اتحمّلت صح.

**تحقق كامل بعد كده**: الأربع نطاقات (`elkheima.com`, `www`, `app`, `owner`)
كلهم `HTTPS 200`، `TLS SAN` يشمل الأربعة بالظبط، `/health` عبر
`app.elkheima.com` رجع `status=ok` (database + redis).

**فجوة إضافية اتصلحت كجزء من نفس الشغلانة**: automation التجديد المُوثّقة في
المشروع (`deploy/systemd/resort-os-certbot-renew.{service,timer}` +
`deploy/certbot/reload-resort-os-nginx.sh`) ماكانتش مثبتة على هذا السيرفر
الجديد خالص (كان بس فيه `snap.certbot.renew.timer` العام، اللي بيجدد الشهادة
لكن من غير أي `nginx -s reload` بعدها — يعني الشهادة الجديدة كانت هتتجدد على
القرص بس متتفعّلش في nginx الشغال فعليًا لحد أول restart يدوي). اتثبّتت الوحدة
الرسمية (`systemctl enable --now resort-os-certbot-renew.timer`)، واتأكد
سكريبت الـ reload شغال صح (`nginx -t` + `nginx -s reload` نجحوا).

**باج حقيقي تاني اتكشف واتصلح فورًا بـ`certbot renew --dry-run`**: الإصدار
الأول استخدم `--standalone` (الطريقة الوحيدة الممكنة وقتها لأن nginx كان
واقع) — ده بيسجّل `authenticator = standalone` في
`/etc/letsencrypt/renewal/elkheima.com.conf`، يعني أي تجديد تلقائي مستقبلي
كان هيحاول يحجز بورت 80 لنفسه ويفشل فورًا (`Could not bind TCP port 80... in
use`) لأن nginx بقى دايمًا شغال ومحتل البورت ده. اتصلح بإعادة إصدار نفس
الشهادة (`--cert-name elkheima.com --force-renewal`) عبر `--webroot -w
/var/www/certbot` بدل `--standalone` — الطريقة دي أصلاً مُجهّزة في
`edge-domain.conf` (location `/.well-known/acme-challenge/`) ومتوافقة مع
nginx شغال بشكل دائم. `certbot renew --dry-run` بعد الإصلاح رجع "all
simulated renewals succeeded" — والشهادة الحقيقية اتأكدت شغالة على الأربع
نطاقات بعد إعادة الإصدار (HTTPS 200 على الأربعة).

## Post-release acceptance (DEPLOYMENT.md §6)

كل البنود اتحققت:
- `docker ps` — كل الـ 9 containers شغالين، الصح منهم `healthy`.
- Image ID واحد مطابق + `org.opencontainers.image.revision=<commit>` عبر
  backend + celery_worker + celery_beat، `RestartCount=0` للثلاثة.
- `alembic current` = `6449668eb81a (head)`.
- Row-count sanity: `users=26`, `branches=1` (بيانات حقيقية، مش فاضية).
- الأربع نطاقات HTTPS 200 من برّه السيرفر، TLS SAN صح.
- DB/Redis لسه loopback-only (مفيش بورت مكشوف).
- لوجات backend/celery/nginx خالية من أي traceback/critical/fatal حقيقي بعد
  استقرار الإصدار.
- مفيش قاعدة بيانات مؤقتة/restore متبقية.
- `/opt/resort-os-current` symlink اتحدّث يشاور على الـ release الجديد.

## ملفات اتلمست على السيرفر (برّه git، توثيق فقط)

- `/opt/resort-os-releases/0e55ac038a8603d2fa4f24e5353a2c9a0288fb45/` (جديد)
- `/opt/resort-os-current` (symlink محدّث)
- `/etc/letsencrypt/live/elkheima.com/*` (شهادة جديدة، أول إصدار على هذا
  السيرفر)
- `/etc/systemd/system/resort-os-certbot-renew.{service,timer}` +
  `/usr/local/sbin/reload-resort-os-nginx` (مثبتين لأول مرة على هذا السيرفر)
- `/var/backups/resort-os/source-releases/` (checksum + rollback image list +
  DB backup الجديدين)

## Rollback (لو احتجناه)

الصور القديمة (REL-22، `2a6cb923f05a9b94d67a19268e38def4ec376084`) لسه متعلّمة
`resort-os-rollback/*:pre-0e55ac03...` مع IDs مسجّلة، والنسخة الاحتياطية لقاعدة
البيانات قبل الـ migration موجودة ومتأكد منها. راجع `DEPLOYMENT.md` §7.
