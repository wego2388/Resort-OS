# DNS-01 / REL-03 — Domain cutover and final production release

**التاريخ:** 2026-07-30
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. النتيجة

أصبح Resort OS يعمل من VPS الخيمة على النطاقات الرسمية:

- Marketing: `https://elkheima.com`
- Marketing alias: `https://www.elkheima.com`
- Staff: `https://app.elkheima.com`

كل خدمات التطبيق موحدة على Resort release `05ee627`، والموقع التسويقي
مبني من release مستقل `e5e122a`. لا يوجد سبب تقني معروف للـrollback وقت
التسليم.

## 2. التفويض والحدود

Mohamed طلب صراحةً تشغيل الدومين وإدارة VPS وإصلاح الأخطاء وتحديث
التوثيق. التغيير اقتصر على:

- edge/DNS/TLS وروابط الإنتاج؛
- إصلاح backup اكتُشف أثناء preflight؛
- إصلاح مصدر build للموقع التسويقي؛
- نشر تدريجي وخطوات rollback وفحص نهائي.

لم تُشغّل migrations أو demo seed في هذه الحزمة، ولم تُعدّل بيانات مالية
أو حجوزات أو مستخدمين. ملف
`scripts/wait-dns-then-switch.sh` لم يُشغّل أو يُعدّل أو يُضمّن في commit.

## 3. المصدر والـcommits

### Resort OS

الفرع:
`claude/CX-02C-frontend-auth-bootstrap`

| commit | الغرض |
|---|---|
| `88e3b2f` | domain TLS edge، health URLs، وتجديد الشهادة مع deploy hook |
| `0b430fb` | domain Compose origins وChatbot routing |
| `aed94a0` | إصلاح backup retention ومسار systemd إلى `current` |
| `05ee627` | تمرير `VITE_PUBLIC_SITE_URL` الصحيح إلى Marketing build |

كل commits مدفوعة إلى
`origin/claude/CX-02C-frontend-auth-bootstrap`. بقي
`origin/main` عند `598938e`.

### Marketing

المستودع:
`/home/wego/projects/elkheima-marketing-website`

commit `e5e122a` على `main`:

- يطلب `VITE_PUBLIC_SITE_URL` في production ويفشل مغلقًا عند غيابه؛
- يوحّد URL المستخدم في constants وSEO؛
- يستبدل روابط IP في HTML وrobots وsitemap بـ`https://elkheima.com`.

نُشر المصدر من archive للـcommit نفسه، وليس من
`/opt/elkheima-marketing-website` القديم غير النظيف. ذلك المجلد بقي محفوظًا
دون تعديل.

## 4. أرشيفات الإصدار

### Resort OS

- active:
  `/opt/resort-os-current -> /opt/resort-os-releases/05ee627`
- archive:
  `/var/backups/resort-os/source-releases/05ee627.tar.gz`
- SHA-256:
  `d8354ec5b48e69a284dc6a6194967ca788f290fe508ba4fd30af0c5bf6946c5b`

### Marketing

- active:
  `/opt/elkheima-marketing-current ->
  /opt/elkheima-marketing-releases/e5e122a`
- archive:
  `/var/backups/resort-os/marketing-source-releases/e5e122a.tar.gz`
- SHA-256:
  `357d28e5a4fab05650f19ba0b9f5f82ea6f10e13e29633d47cad388b45e2aaa2`

ملف `backend/.env.prod` نُقل منفصلًا بصلاحية `0600`. لم تُعرض أسراره.
جرى تحديث القيم غير الحساسة فقط: public origin وCORS وChat host map ومسار
Marketing immutable، ثم نجح `validate_prod_env.py`.

## 5. نقطة التراجع قبل التغيير

- directory:
  `/var/backups/resort-os-domain-cutover-aed94a0`
- mode: `0700`, owner root.
- يحتوي image manifest وDB dump hash ونسخة من إعدادات Let's Encrypt
  السابقة وملفات systemd/health السابقة.
- base source archive:
  `/var/backups/resort-os/source-releases/aed94a0.tar.gz`
- base SHA-256:
  `eb404ef2341e6ca10ff658d00dc2846d6daf81cdd5589d98343c4c1e5bccca72`
- pre-domain images:
  `resort-os-rollback/*:pre-domain-aed94a0`
- pre-Marketing image:
  `resort-os-rollback/marketing-site:pre-e5e122a`
  (`sha256:014777142d8cae6074b13dfee5493f5e7e08f6901797164104292a1b05121c5b`).

## 6. إصلاح النسخ الاحتياطي

كشف preflight أن وجود مجلد rollback محمي داخل
`/var/backups/resort-os` يجعل أمر `find` القديم يدخل المجلد ويفشل بعد أن
ينجح dump نفسه. الإصلاح في `aed94a0`:

- retention/count يقتصر على ملفات dump المباشرة عبر `-maxdepth 1 -type f`;
- systemd backup يعمل من `/opt/resort-os-current`;
- اختُبر السكربت مع nested directory محمي ونجح؛
- شُغلت خدمة backup يدويًا ونجحت.

لا توجد migration أو data transformation مرتبطة بهذا الإصلاح.

## 7. DNS

قبل التغيير:

- `@ A -> 2.57.91.91`, TTL 50.
- `www CNAME -> elkheima.com`, TTL 300.
- لا `app`.

بعد التغيير:

- `@ A -> 191.218.161.133`, TTL 300.
- `app A -> 191.218.161.133`, TTL 300.
- `www CNAME -> elkheima.com`, TTL 300.

استُخدم Hostinger API لتحديث RRsets المحددة فقط. لم يُستخدم Reset DNS،
ولم يُنشأ AAAA أو سجل بريد. Hostinger أكد السجلات بعد التحديث وأنشأ DNS
rollback snapshot:

- snapshot ID: `167902017`
- created: `2026-07-30T03:18:09Z`
- المحتوى: حالة DNS السابقة المذكورة أعلاه.

authoritative nameserver وCloudflare `1.1.1.1` وGoogle `8.8.8.8` وQuad9
`9.9.9.9` أعادوا `191.218.161.133` للجذر و`app`.

## 8. TLS والـedge

- certificate name: `elkheima.com`
- issuer: Let's Encrypt `YE1`
- algorithm: ECDSA
- SAN:
  `elkheima.com`, `www.elkheima.com`, `app.elkheima.com`
- valid:
  `2026-07-30 02:21:35 UTC` إلى `2026-10-28 02:21:34 UTC`
- private key target mode: `0600`
- `certbot renew --dry-run`: passed
- Nginx deploy hook: passed
- HSTS: `max-age=604800` كمرحلة canary، دون `includeSubDomains`
- HTTP على النطاقات الثلاثة يعيد 301 إلى HTTPS.

منفذ Marketing القديم 8443 لم يعد منشورًا. المنافذ العامة للتطبيق هي
80 و443 فقط.

## 9. النشر

1. بُنيت واختُبرت الصور قبل استبدال الحاويات.
2. Marketing canary على منفذ loopback منفصل أعاد:
   `/ = 200`, `/health = 200`, domain files = 4, old-IP files = 0.
3. استُبدل Marketing أولًا وتحقق `elkheima.com = 200`.
4. استُبدلت خدمات التطبيق تدريجيًا من release `05ee627`.
5. PostgreSQL وRedis لم يُعاد إنشاؤهما.
6. وُحّدت labels لكل خدمات التطبيق الست على
   `/opt/resort-os-releases/05ee627`.
7. كل خدمات التطبيق كانت `RestartCount=0` بعد التثبيت.

Image evidence:

- Backend:
  `sha256:17f27751b3cc8855c9fc936b281db58a81f80232ab2669b1eadf5190d6d0b4b4`
- Celery worker:
  `sha256:5b074f225b4ed4dfedb27478f4e55b2738a9510756e0f09b18f8264c36ad6e1b`
- Celery beat:
  `sha256:033e8413d972c29aed8836818e1b35e282c51a0ff76c67857907d15049071d20`
- El Kheima staff app:
  `sha256:f6045dd466411eb6bd600910b4c9ef610cd074e685882116fd5f2f8d1e2a73d2`
- Marketing:
  `sha256:ceffe9aff37f51cdf3a566d144eedad3acb94ab2665acf59f6fe0c04169cb0db`
- Nginx:
  `sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46`

## 10. اختبارات القبول

### Source/Compose

- Resort `agent-check`: passed، 2217 tests collected.
- Alembic single head: `88d1c505a9dc`.
- production env validation: passed.
- domain Compose `config --quiet`: passed.
- Resort archive hashes متطابقة local/VPS.
- Marketing truth/type-check/build: passed.
- Marketing archive hashes متطابقة local/VPS.

### External

- `https://elkheima.com/`: 200.
- `https://www.elkheima.com/`: 200.
- `https://app.elkheima.com/`: 200.
- `https://app.elkheima.com/health`: 200.
- certificate SAN/issuer/dates: matched.
- HSTS موجود على النطاقات الثلاثة.
- HTML: domain ref = 1، old-IP ref = 0.
- robots: domain ref = 1، old-IP ref = 0.
- sitemap: domain refs = 18، old-IP refs = 0.
- 8/8 containers Running، وكل healthchecks المعرّفة healthy، وخدمات
  التطبيق `RestartCount=0`.
- فحص severe logs النهائي لخدمات التطبيق والـedge = 0.

### Chatbot

اختبار زائر خارجي من `elkheima.com`:

- welcome عربي: 97 حرفًا.
- session start: success، token صالح ولم يُطبع.
- live Gemini reply: 399 حرفًا وغير فارغ.
- conversation end: success.

### Data safety

لم يُشغّل importer ضمن DNS-01. ملفات safety counts الخاصة بـDATA-01 تبقى
مرجع عدم تغير المستخدمين والمدفوعات والحجوزات والرواتب:

- `32eb0f8-pre-seed-counts.txt`
- `32eb0f8-post-seed-safety-counts.txt`
- read-only account count بعد آخر فحص:
  `super_admin total=1, active=1`؛ لا حسابات موظفين أخرى. إنشاء الحسابات
  ينتظر roster حقيقيًا، ولا تُختلق هويات demo.

### Final backup/health

- آخر DB dump:
  `/var/backups/resort-os/resort_os_20260730_043330.dump`
- SHA-256:
  `a31e43e74d777ec41a93ca30a4ec3270b2f1995fb34846b36591498a4e23b72d`
- `pg_restore --list` داخل PostgreSQL 16 معزول: passed.
- `resort-os-backup.service` و`resort-os-healthcheck.service`: manual run
  passed بعد آخر استبدال.
- أزيل extraction staging غير الفعال `0b430fb` فقط بعد التحقق من عدم وجود
  مرجع runtime إليه؛ أرشيفه ما زال محفوظًا وقابلًا للاستعادة.

## 11. التوافق والترحيل

- لا migration جديدة في حزمة DNS-01.
- Alembic بقي عند `88d1c505a9dc`.
- schema وPostgreSQL volumes لم تتغير.
- rollback تطبيقي متوافق لا يستدعي database restore.

## 12. خطة التراجع

عند عطل مثبت فقط:

1. استخدم image manifest ووسوم rollback داخل نقطة cutover.
2. أعد خدمات التطبيق بالتدرج نفسه.
3. أعد DNS من snapshot `167902017` إذا كان الرجوع إلى المضيف السابق قرارًا
   مقصودًا، وليس لمشكلة تطبيق قابلة للإصلاح.
4. لا تستعد DB إلا عند إثبات تلف بيانات وتحديد dump مناسب.
5. أعد فحص DNS/TLS/HTTP/DB/Redis/containers/logs بعد الرجوع.

## 13. المتبقي

- UAT ميداني بالأجهزة والأدوار واللغتين.
- اعتماد master data الحقيقية بدل بيانات العرض.
- QR/guest alerts/printing/offline/Night Audit/POS field tests.
- قناة خارجية لفشل health gate وburn-in.
- provider snapshot دوري كطبقة إضافية، لا كبديل للنسخة المشفرة.
- دليل الإدارة والتدريب العربي موجود في `docs/STAFF_APP_GUIDE_AR.md`
  لتنفيذ UAT واعتماد كل موظف، ويكمله `docs/SUPER_ADMIN_GUIDE_AR.md`.

## 14. حالة Git والنشر

- Resort source commits حتى `05ee627`: committed, pushed, deployed.
- Marketing `e5e122a`: committed, pushed, deployed.
- Resort `origin/main`: unchanged at `598938e`.
- هذا handoff وتحديثات الحالة جزء من commit توثيق ما بعد النشر على فرع
  Resort OS نفسه.
- user-owned `scripts/wait-dns-then-switch.sh`: untracked, untouched,
  unstaged.
