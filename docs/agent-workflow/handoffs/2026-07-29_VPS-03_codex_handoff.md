# VPS-03 — اتصال الإدارة والتدقيق النهائي قبل مصالحة مصدر الإنتاج

**التاريخ:** 2026-07-29 (Africa/Cairo)
**المنفذ والمراجع النهائي:** Codex، بتكليف Mohamed
**الحالة:** VERIFIED / DEPLOY_PAUSED_FOR_SOURCE_RECONCILIATION

## القرار والنطاق

- الخيمة تعمل بفرع تشغيلي واحد فقط حاليًا؛ لا Branch Switcher ظاهر.
- الإصدار الحالي IP-only على `191.218.161.133`؛ لا DNS أو domain switch دون قرار صريح جديد.
- التدقيق تم دون قراءة أسرار أو عرضها، ودون deploy أو تغيير بيانات أو حاويات.

## الوصول الإداري المثبت

- SSH alias: `resort-os-vps` → `191.218.161.133:22`.
- المستخدم: `resortos`، عضو `sudo` و`docker`، و`sudo -n` ناجح.
- `permitrootlogin no`، `passwordauthentication no`، `pubkeyauthentication yes`.
- Hostname: `resort-os-prod`، Ubuntu 24.04/kernel `6.8.0-136-generic`.
- لا حاجة ولا سماح بإعادة تفعيل root password أو Reset SSH/Firewall من لوحة Hostinger.

## الأمن والموارد

- UFW active: default deny incoming؛ 22 limited و80/443/8443 allowed.
- Fail2ban sshd active؛ لا IPs محظورة وقت الفحص.
- PostgreSQL `5436` وBackend `8005` وRedis `6381` loopback-only.
- القرص 9.5/96GB (10%)، الذاكرة المتاحة 5.8/7.8GiB، ولا failed systemd units.
- المنفذ 8443 ما زال مؤقتًا للتسويق IP-TLS UAT ويحتاج قرار إغلاق بعد UAT.

## حالة التطبيق الحية

- Compose project `resort-os-prod`، 8 حاويات Running.
- Backend وEl Kheima وCelery worker/beat وPostgreSQL وRedis healthy حيث توجد healthchecks.
- Backend image بدأ 2026-07-29 15:51 UTC، healthy، restart count = 0.
- `GET http://127.0.0.1:8005/health` أعاد 200.
- compose metadata: `docker-compose.prod.yml` + `docker-compose.prod.ip-only.yml` وملف البيئة `backend/.env.prod`؛ لم تُقرأ قيمه.

## النسخ والتراجع

- `resort-os-backup.timer` enabled؛ آخر تشغيل 2026-07-29 03:03 UTC Result=success.
- 4 dumps يومية موجودة في `/var/backups/resort-os`، ونسخة pre-deploy في `/opt/resort-os/backups`.
- `pg_restore --list` نجح على أحدث dump؛ هذا تحقق بنيوي وليس restore drill كاملًا.
- لوحة Hostinger في الصور تعرض 0 snapshots و0 provider backups؛ لا توجد حماية offsite مثبتة.

## TLS

- شهادة Let's Encrypt للـIP صالحة حتى 2026-08-02 09:59 UTC.
- `resort-os-certbot-renew.timer` يعمل كل 12 ساعة.
- `certbot renew --cert-name 191.218.161.133 --dry-run` نجح في 2026-07-29.
- لذلك domain ليس شرطًا لتفادي الانتهاء؛ لا تغيير DNS ضمن هذه الحزمة.

## مانع النشر المكتشف

- `/opt/resort-os` عند Git SHA `0a13c97` على `main`/`origin/main`.
- الشجرة تحتوي 79 ملفًا tracked معدلًا وملفات untracked، و`git diff` يقارب 2210 additions/524 deletions.
- الصور العاملة اليوم بُنيت من هذه الحالة غير الملتزم بها، فلا يعبّر SHA وحده عن exact source.
- أي `git pull`, reset, rsync أو rebuild مباشر قد يفقد مصدر الإصدار العامل؛ ممنوع حتى المصالحة.

## التحقق المحلي المرتبط

- branch `claude/CX-02C-frontend-auth-bootstrap` عند `598938e` مع تغييرات نهائية مقصودة.
- full backend انتهى 100% بصفر failure؛ 63 targeted passed.
- frontend 93/93؛ type-check/build وagent-check وgit diff check ناجحة.
- Alembic single head: `88d1c505a9dc`.

## مسار التنفيذ التالي المحكوم

1. أخذ provider snapshot أو نسخة offsite قابلة للاسترجاع قبل أي deploy.
2. حفظ manifest وpatch/bundle exact للحالة الحية، مع checksums ووقت البناء.
3. مصالحة تغييرات الخادم مع commits المحلية `258c99c` و`598938e` وحزمة المراجعة النهائية.
4. إنشاء commit واحد قابل للمراجعة دون تضمين أسرار أو ملف المستخدم `scripts/wait-dns-then-switch.sh`.
5. إعادة gates من المصدر الملتزم، ثم pre-deploy DB backup واختبار rollback.
6. deploy controlled للصورتين المطلوبتين فقط، health/UAT سريع، ثم مراقبة وإثبات SHA/image digests.

## تغييرات الإنتاج في هذه الحزمة

- لا deploy، لا restart، لا DNS، لا تعديل firewall/SSH/secrets/data.
- الأثر الوحيد: Certbot staging dry-run وسجله التشغيلي؛ شهادة الإنتاج لم تُستبدل.
