# لوحة التنفيذ الحية — El Kheima

**آخر تحديث:** 2026-07-29
**المالك:** Mohamed
**قائد التنفيذ والمراجع النهائي:** Codex
**المرحلة الحالية:** OPS-01 + UAT-01 — burn-in وقبول تشغيلي بعد REL-02
**قرار الإطلاق:** IP-only؛ domain/DNS paused

> هذه اللوحة تعرض المهمة الحالية فقط. التفاصيل والبوابات في
> `docs/audits/EL_KHEIMA_FINAL_EXECUTION_PLAN_AR.md`. أي لوحة أو موجز أقدم
> تحت `docs/archive/` تاريخي وممنوع التنفيذ منه.

## قرارات سارية

- فرع تشغيلي واحد للخيمة؛ لا Branch Switcher ظاهر.
- العزل والصلاحيات fail-closed في الـBackend والواجهة والطابور غير المتصل.
- Codex ينفذ ويراجع نهائيًا؛ Mohamed يعتمد القرارات التجارية والبيانات وGo/No-Go.
- أي تغيير إنتاج جديد يحتاج backup وrollback وhealth evidence.
- لا DNS/domain switch بلا قرار جديد.
- ملف `scripts/wait-dns-then-switch.sh` غير نشط ولا يُلمس.

## المهمة الجارية

| الحزمة | الحالة | النتيجة المطلوبة | المانع |
|---|---|---|---|
| SRC-01 — production exact-source preservation | COMPLETE | bundle+patch+untracked+checksums أُعيد تركيبها | — |
| SRC-02 — reconcile live/local/Git | COMPLETE | لا source مجهول؛ 77/88 متطابق والباقي مصنف | — |
| REL-01 — reviewed release source | COMPLETE | commits حتى `ac7764f` مدفوعة على فرع العمل | — |
| DR-01 — off-server recovery point | COMPLETE | encrypted DB + full isolated restore evidence | — |
| REL-02 — controlled deploy | COMPLETE | immutable release + digests + health + rollback | — |
| OPS-01 — burn-in and alerting | BASELINE COMPLETE | health gate كل 5 دقائق؛ إرسال خارجي | اختيار قناة التنبيه |
| UAT-01 — operational acceptance | PENDING | جهاز/دور/لغة/شبكة/مال | ممثلو التشغيل والمالية |
| DATA-01 — approved master data | BLOCKED ON INPUT | غرف/أسعار/مخزون/مالية معتمدة | المالك والتشغيل |

## ما اكتمل في الجولة الحالية

- [x] فهم الخطة والتعديلات الجديدة.
- [x] تثبيت قرار الفرع التشغيلي الواحد وإزالة selector الظاهر.
- [x] frontend bootstrap/effective permissions/route/action gates.
- [x] offline queue identity = user + branch + module.
- [x] إصلاح refs ومسار Night Audit ومراجعة migration downgrade.
- [x] full backend 100% بصفر failure.
- [x] 63 targeted backend و93/93 frontend.
- [x] type-check/build/agent-check/Alembic single-head/diff-check.
- [x] SSH admin access + sudo/Docker.
- [x] SSH/UFW/Fail2ban/listeners/resources audit.
- [x] 8-container health وHTTP 200.
- [x] backup status + archive structure check.
- [x] Certbot IP renewal dry-run.
- [x] أرشفة تعليمات الوكلاء/deploy/domain المتعارضة.
- [x] exact-source archive محلي وخارجي مع SHA-256.
- [x] إعادة تركيب production worktree byte-for-byte في clone مؤقت.
- [x] مصالحة 674 live source path مع 682 local path بلا mode drift أو source مجهول.
- [x] commit الكود النهائي `6c9f09e` بعد final gate أخضر.
- [x] encrypted off-server DB backup مع matching decrypted hash.
- [x] isolated full restore: 135 tables، Alembic `c4d8e2f6a901`، cleanup confirmed.
- [x] push لفرع العمل حتى `ac7764f` مع بقاء `origin/main` بلا تغيير.
- [x] immutable release archive وSHA-256 مثبتان على الـVPS.
- [x] pre-deploy DB dump وrollback image tags قبل استبدال الخدمات.
- [x] preflight للصورة الجديدة وAlembic head `88d1c505a9dc`.
- [x] نشر متدرج للـBackend وCelery وEl Kheima ثم إعادة إنشاء Nginx.
- [x] 8/8 containers running؛ الصور الجديدة restarts=0.
- [x] staff 443 وmarketing 8443 و`/health` يعيدون 200 من خارج الخادم.
- [x] فحص DB/Redis/counts/TLS/listeners/recent severe logs ناجح.
- [x] نقل `wagdy.md` و`PROJECT_STATUS.md` التاريخيين للأرشيف وإنشاء نسخ حية مختصرة.
- [x] تثبيت `resort-os-healthcheck.timer` كل 5 دقائق؛ manual systemd run = 14/14.

## حالة الإنتاج المثبتة

| البند | النتيجة |
|---|---|
| Host/IP | `resort-os-prod` / `191.218.161.133` |
| SSH | key-only، `resortos`، sudo/Docker |
| Containers | 8 Running؛ healthchecks ناجحة |
| Backend | healthy، `/health` 200، restarts=0 |
| Ports | 5436/6381/8005 loopback-only؛ 80/443/8443 public |
| Release | `/opt/resort-os-releases/ac7764f`؛ compose IP-TLS |
| Active images | backend/Celery/El Kheima من digests REL-02؛ restarts=0 |
| Legacy Git tree | `0a13c97` dirty محفوظ وغير مستخدم كمصدر للحاويات الجديدة |
| Backup | daily local + fresh pre-deploy dump |
| Offsite/provider | encrypted verified restore موجود؛ Hostinger snapshot count = 0 |
| TLS | IP cert حتى 2026-08-02؛ dry-run success |
| Database | Alembic `88d1c505a9dc`؛ users=1، branches=1، online bookings=0 |
| Monitoring | timer enabled/active؛ 14 health checks؛ journal يحتفظ بالفشل |
| Failed units | 0 |

## الأدلة التشغيلية

- VPS archive:
  `/var/backups/resort-os/source-snapshots/20260729T194312Z.tar.gz`
- Local archive:
  `/home/wego/backups/resort-os/production-source/20260729T194312Z.tar.gz`
- SHA-256:
  `71b7bb408b2e0be822d4f2e212fa26c37f32f8761b770d0585efd37e76ed50b3`
- Reconciliation:
  `/home/wego/backups/resort-os/production-source/reconciliation-20260729T194312Z/`
- Release archive:
  `/var/backups/resort-os/source-releases/ac7764f.tar.gz`
- Release archive SHA-256:
  `17251e23660d7f84d6e89bdb0e2a0b5986ff637f2768a2cbf82589462984d6e6`
- Rollback images:
  `/var/backups/resort-os/source-releases/ac7764f-rollback-images.txt`

## آخر تسليم

`docs/agent-workflow/handoffs/2026-07-29_OPS-01_codex_handoff.md`

## التحديث التالي المطلوب

راقب الإصدار بعد النشر، ثبّت قناة alerts، ثم نفّذ UAT بالأجهزة والأدوار
والبيانات المعتمدة. لا domain/DNS ولا Chatbot activation ضمن هذه الحزمة.
