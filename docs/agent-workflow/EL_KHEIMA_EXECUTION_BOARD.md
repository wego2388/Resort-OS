# لوحة التنفيذ الحية — El Kheima

**آخر تحديث:** 2026-07-29
**المالك:** Mohamed
**قائد التنفيذ والمراجع النهائي:** Codex
**المرحلة الحالية:** REL-02 — production preflight قبل push/deploy المحكوم
**قرار الإطلاق:** IP-only؛ domain/DNS paused

> هذه اللوحة تعرض المهمة الحالية فقط. التفاصيل والبوابات في
> `docs/audits/EL_KHEIMA_FINAL_EXECUTION_PLAN_AR.md`. أي لوحة أو موجز أقدم
> تحت `docs/archive/` تاريخي وممنوع التنفيذ منه.

## قرارات سارية

- فرع تشغيلي واحد للخيمة؛ لا Branch Switcher ظاهر.
- العزل والصلاحيات fail-closed في الـBackend والواجهة والطابور غير المتصل.
- Codex ينفذ ويراجع نهائيًا؛ Mohamed يعتمد القرارات التجارية والبيانات وGo/No-Go.
- لا deploy قبل source reconciliation وoffsite rollback point.
- لا DNS/domain switch بلا قرار جديد.
- ملف `scripts/wait-dns-then-switch.sh` غير نشط ولا يُلمس.

## المهمة الجارية

| الحزمة | الحالة | النتيجة المطلوبة | المانع |
|---|---|---|---|
| SRC-01 — production exact-source preservation | COMPLETE | bundle+patch+untracked+checksums أُعيد تركيبها | — |
| SRC-02 — reconcile live/local/Git | COMPLETE | لا source مجهول؛ 77/88 متطابق والباقي مصنف | — |
| REL-01 — local final commit | COMPLETE | code `6c9f09e` + documentation commit | — |
| DR-01 — off-server recovery point | COMPLETE | encrypted DB + full isolated restore evidence | — |
| REL-02 — controlled deploy | IN PROGRESS | preflight ثم image digests + health + rollback | preflight |
| UAT-01 — operational acceptance | PENDING | جهاز/دور/لغة/شبكة/مال | REL-02 + ممثلي UAT |

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

## حالة الإنتاج المثبتة

| البند | النتيجة |
|---|---|
| Host/IP | `resort-os-prod` / `191.218.161.133` |
| SSH | key-only، `resortos`، sudo/Docker |
| Containers | 8 Running؛ healthchecks ناجحة |
| Backend | healthy، `/health` 200، restarts=0 |
| Ports | 5436/6381/8005 loopback-only؛ 80/443/8443 public |
| Git | `0a13c97` + 79 tracked modified + untracked |
| Backup | daily local success؛ structural check passed |
| Offsite/provider | غير مثبت؛ Hostinger count = 0 |
| TLS | IP cert حتى 2026-08-02؛ dry-run success |
| Failed units | 0 |

## أدلة SRC-01/SRC-02

- VPS archive:
  `/var/backups/resort-os/source-snapshots/20260729T194312Z.tar.gz`
- Local archive:
  `/home/wego/backups/resort-os/production-source/20260729T194312Z.tar.gz`
- SHA-256:
  `71b7bb408b2e0be822d4f2e212fa26c37f32f8761b770d0585efd37e76ed50b3`
- Reconciliation:
  `/home/wego/backups/resort-os/production-source/reconciliation-20260729T194312Z/`

## آخر تسليم

`docs/agent-workflow/handoffs/2026-07-29_DR-01_codex_handoff.md`

## التحديث التالي المطلوب

افحص production counts/config-presence وrunbook/compose exact commands دون
عرض أسرار، ثم قرر Go/No-Go للنشر. لا domain/DNS ضمن REL-02.
