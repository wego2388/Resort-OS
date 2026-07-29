# OPS-01 — production health monitoring baseline

**التاريخ:** 2026-07-29
**المنفذ والمراجع:** Codex
**الحالة:** BASELINE COMPLETE

## النتيجة

أُضيف health gate read-only للإنتاج يعمل كل خمس دقائق عبر systemd. لا يغيّر
حاويات أو بيانات، ويخرج non-zero عند فشل أي شرط حتى يظهر failure صراحةً في
systemd journal.

## المصدر والتثبيت

- source commits: `538523a` ثم إصلاح parser في `ac0b52b`.
- script: `scripts/check_prod_health.sh`.
- units:
  - `deploy/systemd/resort-os-healthcheck.service`
  - `deploy/systemd/resort-os-healthcheck.timer`
- installed script:
  `/usr/local/lib/resort-os/check-prod-health.sh`، mode `0755`، root:root.
- installed units: `/etc/systemd/system/resort-os-healthcheck.{service,timer}`,
  mode `0644`، root:root.
- admin recovery/create/first-branch wrappers ثُبتت من نفس المصدر تحت
  `/usr/local/lib/resort-os/`، mode `0755`، root:root، وتكتشف release الفعال.
- النقل إلى الـVPS تحقق من SHA-256 قبل `install`.
- timer: enabled وactive، interval خمس دقائق.

## التغطية

1. Backend health payload وDB وRedis.
2. Staff HTTPS على 443.
3. Marketing HTTPS على 8443.
4. وجود وحالة health لكل الحاويات الثماني.
5. وجود dump غير فارغ أحدث من 26 ساعة.
6. صلاحية TLS لأكثر من 48 ساعة.
7. استخدام root disk أقل من 85%.

## التحقق

- `bash -n`: passed.
- failure-path محلي متعمد: exit 1 مع قائمة failures.
- أول تشغيل على الـVPS كشف parser regex هشًا رغم أن التطبيق healthy؛ لم
  يُخفَ الفشل.
- استُبدل parser بفحص ثابت لعقد JSON الحالي في commit `ac0b52b`.
- تشغيل updated script مباشرة على الـVPS: `RESORT_HEALTHCHECK_OK passes=14`.
- تشغيل updated service يدويًا: `Result=success`, `ExecMainStatus=0`.
- حالة timer: enabled/active.
- أول trigger تلقائي: `2026-07-29 20:45:55 UTC`،
  `RESORT_HEALTHCHECK_OK passes=14`, `Result=success`, `ExecMainStatus=0`.
- الموعد التلقائي التالي سُجّل بعد خمس دقائق، و`systemctl --failed` = صفر.

## المتبقي

- وجهة إشعار خارجية عند الفشل غير متاحة بعد. يلزم اختيار قناة يملكها Mohamed
  (email/webhook/خدمة مراقبة) وإعداد سرها خارج Git.
- systemd journal والفشل non-zero يوفران baseline محليًا، لكنهما لا يضمنان
  إخطارًا إذا فُقد الخادم بالكامل؛ external uptime monitor هو التحسين التالي.
