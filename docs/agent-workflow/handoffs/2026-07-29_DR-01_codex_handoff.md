# DR-01 — نسخة قاعدة بيانات مشفرة خارج الخادم واختبار استعادة

**التاريخ:** 2026-07-29 (Africa/Cairo)
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## artifact

- Encrypted DB:
  `/home/wego/backups/resort-os/database/resort_os_20260729_030303.dump.gpg`
- Recovery manifest:
  `/home/wego/backups/resort-os/database/README.md`
- Key location:
  `/home/wego/.config/resort-os/offsite-backup.pass`
- Source SHA-256:
  `351ece7b8356fe0ae39740e07a8867be320e23072627b4d59dd0e9ab99de557f`
- Encrypted SHA-256:
  `7678ae65e688ae7d734d034519512440d21e1138424ceb3febd94467f64a0839`
- source/encrypted sizes: `539393` / `539708` bytes.
- artifact/key/checksum/manifest modes: `0600`.

لم يُكتب dump غير مشفر على الجهاز المحلي. انتقل plaintext داخل SSH ثم دخل
GnuPG مباشرةً، والمفتاح خارج المستودع ولم يُعرض.

## verification

1. فك تشفير stream أعاد SHA-256 المصدر نفسه.
2. استُعيد stream داخل قاعدة PostgreSQL مؤقتة محددة:
   `resort_os_restore_verify_20260729_2300`.
3. `pg_restore --exit-on-error --no-owner --no-privileges` نجح.
4. public tables = 135.
5. Alembic version = `c4d8e2f6a901`.
6. حُذفت قاعدة الاختبار، وفحص مستقل أكد غيابها.
7. Backend/PostgreSQL/El Kheima ظلت healthy.
8. `/health` أكد application وdatabase وRedis جميعها OK.

ظهر quoting error في استعلام pre-existence تمهيدي، لكن `createdb` نجح بعده
(ما يثبت عدم وجود الاسم)، والاستعادة والتحقق والحذف المستقل كلها نجحت. لم
يؤثر ذلك في قاعدة الإنتاج.

## حدود الحماية

- تحقق الحد الأدنى لاستعادة البيانات عند فقد الـVPS.
- Hostinger ما زال يعرض صفر provider snapshots/backups.
- المفتاح والنسخة على workstation واحد؛ يلزم لاحقًا نسخ المفتاح/الـartifact
  إلى وجهة منفصلة مضبوطة.
- RPO الحالي يقارب 24 ساعة من timer اليومي.
- زمن الاختبار الحالي لا يُعتمد RTO ثابتًا لأن قاعدة البيانات ما زالت صغيرة.

## القرار

DR-01 COMPLETE. REL-02 يمكنه دخول preflight، لكن لا deploy إلا بعد فحص
production counts، متطلبات encryption/migration، compose exact files،
والـrollback command. لا DNS/domain change في هذه الحزمة.
