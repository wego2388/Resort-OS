# MKT-02 — Timeshare and multilingual Marketing release

**التاريخ:** 2026-07-30
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## النتيجة

نُشر Marketing release `16f8f2c` على `elkheima.com` من المصدر المستقل:

- صفحة `/timeshare` بأربع لغات.
- Blue Bay ظاهرة كجهة إدارة الملكية الجزئية، وفق نموذج الحجز الداخلي
  المقدم من المالك والمؤرخ في 9 يونيو 2026.
- الطلب يمر عبر `/api/v1/hub/contact` مع consent وidempotency، ولا ينشئ
  سعرًا أو حجزًا أو التزامًا ماليًا.
- صور الأنشطة والزفاف والحفلات راجعها Codex بصريًا. صورة Corporate
  المقترحة كانت صورة زفاف؛ لم تُنشر واستُخدمت صورة فعالية جماعية موجودة.
- خريطة الموقع الجديدة بقيت خلف
  `PUBLIC_TRUTH.publish.exactLocation=false`.
- `PUBLIC_TRUTH.publish.prices=false` لم يتغير.

## المصدر والجودة

- repo: `elkheima-marketing-website`
- branch: `main`
- commit:
  `16f8f2cf76a84dd815ae292f9f0e38a776489fc4`
- GitHub `main` يطابق الالتزام.
- `npm run validate:truth`: passed.
- `npm run type-check`: passed.
- `npm run build`: passed.
- i18n parity:
  `2919` مفتاحًا لكل من `ar`, `en`, `ru`, `it`؛ صفر missing.
- المراجعة البصرية العربية والإنجليزية: passed؛ لا أخطاء تطبيق في
  جلسات الفحص.
- صورة Tube Boat ضُغطت من نحو 914KB إلى 226KB مع بقاء دقة
  `1600x1068`.

تحذيرا البناء غير الحاجزين: استيراد العربية static/dynamic معًا، وchunk
`public-pages` أكبر من 500KB.

## الإصدار والتراجع

- active:
  `/opt/elkheima-marketing-current ->
  /opt/elkheima-marketing-releases/16f8f2c`
- archive:
  `/var/backups/resort-os/marketing-source-releases/16f8f2c.tar.gz`
- archive SHA-256:
  `ba3d8d5c25c8487fb75906ce17ca3ffe8c0df9f0a087c0afefb478c9129cf7a9`
- image:
  `sha256:277ff191eb630c4313ff728aabfda5e3fbc205c72432e97408b13c03d7358d2e`
- rollback tag:
  `resort-os-rollback/marketing-site:pre-16f8f2c`
- rollback manifest:
  `/var/backups/resort-os/marketing-source-releases/16f8f2c-rollback-image.txt`
- pre-release DB:
  `/var/backups/resort-os/database/resort_os_20260730_143944.dump`
- DB SHA-256:
  `1358f16a526240b447bff98570a93eda9ee8933d8a94580ee5e8ec12c3987e04`
- `pg_restore --list`: passed.

## قبول الإنتاج

- canary `/` و`/timeshare`: passed.
- Blue Bay موجودة في 4 ملفات bundle.
- old-IP references في bundle: صفر.
- apex و`www` و`/ar/timeshare` و`/en/timeshare`: HTTP 200.
- `app.elkheima.com/health`: HTTP 200.
- 8 حاويات Running؛ مجموع `RestartCount=0`.
- Marketing container: running، `RestartCount=0`.
- severe logs: صفر.
- systemd health gate:
  `Result=success`, `ExecMainStatus=0`.

لم تُعد حاويات PostgreSQL أو Redis أو Resort، ولم يتغير schema أو DNS أو
TLS في هذه الحزمة.
