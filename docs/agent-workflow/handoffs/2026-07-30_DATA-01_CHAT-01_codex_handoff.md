# DATA-01-DEMO + CHAT-01 — production handoff

**التاريخ:** 2026-07-30
**المنفذ والمراجع النهائي:** Codex
**النتيجة:** COMPLETE / PASSED
**النطاق:** بيانات synthetic واقعية + Backend deploy + Chatbot live verify
**DNS:** REVIEWED ONLY؛ لم يتغير

## النتيجة

نُشرت حزمة بيانات عرض مترابطة وآمنة للفرع الوحيد `ELK-001` عبر importer
صريح وقابل للتكرار من commit `32eb0f8`. لم يُستخدم `app.seed`، ولم تُنشأ
هوية أو معاملة مالية أو حجز تجريبي. بعد النشر اجتاز Chatbot دورة حية كاملة
بالعربية عبر Gemini.

## ضوابط importer

- dry-run هو الوضع الافتراضي.
- التطبيق يحتاج النص الحرفي `APPLY EL KHEIMA SYNTHETIC DEMO V1`.
- لا يعمل إلا مع فرع فعال واحد بالكود `ELK-001` وsuper admin فعال واحد.
- PostgreSQL advisory lock يمنع التشغيل المتوازي.
- audit marker: `synthetic_demo_dataset_seeded` / `2026-07-30.1`.
- التشغيل الثاني على الإنتاج أعاد `added={}`.
- الموردون بلا هاتف/بريد؛ CRM بلا بيانات اتصال؛ Hub draft/inactive؛ عقود
  timeshare وlease draft؛ B2B inactive؛ أعمال الصيانة مغلقة أو ملغاة.

## البيانات المضافة

| النطاق | العدد |
|---|---:|
| warehouses / inventory categories / products | 3 / 10 / 114 |
| opening stock movements | 114 |
| suppliers / purchase orders / purchase requests | 6 / 5 / 3 |
| dining outlets / items / recipe lines / tables | 2 / 104 / 459 / 12 |
| room types / rooms / rate plans | 5 / 52 / 4 |
| departments / assets / work orders | 12 / 6 / 3 |
| CRM customers / leads / opportunities / campaigns | 4 / 4 / 2 / 1 |
| timeshare units / draft contracts | 12 / 3 |
| draft lease contracts | 3 |
| demo beach locations / inactive B2B contracts | 8 / 2 |
| Hub content | 3 draft pages + 1 inactive offer + 1 draft blog |

## حدود السلامة

لم تتغير أعداد `users` أو `journal_entries` أو `payments` أو
`payroll_runs` أو `bookings` أو `dining_orders` أو `beach_transactions`
أو `timeshare_installments` أو `lease_payments`. دليلا ما قبل/بعد متطابقان:

- `/var/backups/resort-os/source-releases/32eb0f8-pre-seed-counts.txt`
- `/var/backups/resort-os/source-releases/32eb0f8-post-seed-safety-counts.txt`

لا guest alerts أو notifications أو public bookings أو active outbound
contact data ضمن الحزمة.

## الجودة

- full backend: 2217 tests collected، exit 0، صفر failure.
- importer tests: 9 passed.
- clean PostgreSQL apply + second apply + safety counts: passed.
- production dump restore + apply/idempotency + unchanged existing financial
  and beach transaction counts: passed؛ temporary DB cleanup confirmed.
- Alembic current/head: `88d1c505a9dc`؛ لا schema migration.
- ruff و`git diff --check` و`agent-check`: passed.

## النسخ والتراجع والنشر

- source archive:
  `/var/backups/resort-os/source-releases/32eb0f8.tar.gz`
- archive SHA-256:
  `a1ba17a840afe15191451e21a3a08ee604147cb6b5722c582ed0f891e88c16e3`
- pre-demo dump:
  `/opt/resort-os-releases/32eb0f8/backups/resort_os_20260729_233436.dump`
- dump SHA-256:
  `dd7499b025bbd46ccdbd9b8544531b129a0be035e49f46c90483b75ee4f1b3ff`
- encrypted off-server copy:
  `/home/wego/backups/resort-os/database/resort_os_20260729_233436.dump.gpg`
- rollback image:
  `resort-os-rollback/backend:pre-32eb0f8`
- new Backend image:
  `sha256:17f27751b3cc8855c9fc936b281db58a81f80232ab2669b1eadf5190d6d0b4b4`
- active Backend release: `/opt/resort-os-releases/32eb0f8`

استُبدل Backend فقط. بقيت صور Celery وEl Kheima وبقية الخدمات بلا تغيير.
بعد إعادة حل الـproxy: 8 حاويات Running، Backend healthy/restarts=0،
HTTPS 443/8443 = 200، وapp/DB/Redis = ok.

## Chatbot

الواجهة تعرض الـwidget فعليًا، وبيئة الإنتاج تحتوي provider key مع
`CHAT_PROVIDER_DATA_GOVERNANCE_VERIFIED=true`. نجح الاختبار الحي:

1. إنشاء session.
2. قبول AI disclosure.
3. إرسال سؤال عربي synthetic بلا PII.
4. استلام رد Gemini.
5. إنهاء session.

لم تُطبع أو تُحفظ token أو قيمة سرية. متغير build
`VITE_CHATBOT_ENABLED` موجود في Docker plumbing لكنه ليس enforcement داخل
المصدر الحالي؛ هذه ملاحظة تنظيف منخفضة الأولوية وليست عطلًا تشغيليًا.

## DNS

المراجعة كانت read-only:

- `elkheima.com A = 2.57.91.91`، وهو المضيف القديم.
- `www CNAME = elkheima.com` ويحل إلى العنوان القديم نفسه.
- لا AAAA ولا CAA وقت التحقق.
- لا MX/TXT/DMARC/DKIM ظاهرة وقت التحقق.
- nameservers: `pixel.dns-parking.com` و`byte.dns-parking.com`.
- VPS المشروع: `191.218.161.133`.
- HTTP يعيد 200 من المضيف القديم، لكن HTTPS للجذر و`www` يفشل وقت التحقق
  بـTLS internal alert.

لا DNS cutover ضمن هذا التسليم. عند اعتماد الانتقال يجب أولًا تجهيز شهادة
domain وNginx، وإضافة سجلات البريد إن كانت مطلوبة، ثم تغيير `A @` فقط إلى
عنوان الـVPS مع الإبقاء على CNAME `www`. لا تستخدم Reset DNS، ولا تضف
AAAA بلا IPv6 فعلي.

## المتبقي

- UAT على هاتف وجهاز وبأدوار عربية/إنجليزية ومسارات QR/offline/POS.
- مراجعة demo واعتماد master data الحقيقية والمالية بدلها تدريجيًا.
- قناة خارجية لتنبيه healthcheck وburn-in.
- قرار مستقل وصريح قبل domain cutover.
