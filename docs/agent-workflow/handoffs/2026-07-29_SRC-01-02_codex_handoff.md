# SRC-01/SRC-02 — حفظ ومصالحة مصدر الإنتاج

**التاريخ:** 2026-07-29 (Africa/Cairo)
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE
**تغييرات الإنتاج:** لا deploy أو restart أو DNS أو data/secret change

## النتيجة

حُفظ exact source للإصدار العامل بعيدًا عن `/opt/resort-os`، ونُقل إلى الجهاز
المحلي، ثم أُعيد تركيبه في clone مؤقت. الـbinary patch والملفات untracked
الناتجة تطابقت byte-for-byte مع اللقطة؛ لم يعد Git SHA القديم وحده هو نقطة
الرجوع الوحيدة.

## artifacts

- VPS directory:
  `/var/backups/resort-os/source-snapshots/20260729T194312Z`
- VPS archive:
  `/var/backups/resort-os/source-snapshots/20260729T194312Z.tar.gz`
- Local archive:
  `/home/wego/backups/resort-os/production-source/20260729T194312Z.tar.gz`
- Local reconciliation reports:
  `/home/wego/backups/resort-os/production-source/reconciliation-20260729T194312Z/`
- SHA-256:
  `71b7bb408b2e0be822d4f2e212fa26c37f32f8761b770d0585efd37e76ed50b3`
- Archive size: `6,591,688` bytes.
- Local permissions: `0600`.

## محتوى اللقطة

- complete Git bundle عند base `0a13c97ab4abff334c70260b5a27330becead318`.
- full-index binary worktree patch.
- staged index patch.
- untracked source tar وقائمة مسارات.
- Git status/log/diff metadata.
- Docker runtime/image IDs ووقت الإنشاء، دون environment values.
- SHA256SUMS لكل ملف داخلي.

لم تشمل اللقطة ignored `.env` أو dump قاعدة البيانات أو private key. فحص مسارات
untracked وفحص private-key markers نجح قبل الضغط.

## إثبات إعادة التركيب

1. تحقق SHA-256 للأرشيف الخارجي.
2. تحقق كل `SHA256SUMS` الداخلية.
3. `git bundle verify` أكد complete history وثلاثة refs عند `0a13c97`.
4. clone جديد من bundle.
5. `git apply --check` ثم تطبيق worktree patch.
6. استعادة untracked tar بعد فحص منع absolute/`..` paths.
7. إعادة توليد patch وقائمة untracked ومقارنتهما بـ`cmp`.
8. النتيجة: `RECONSTRUCTION=EXACT`.

تحذيرا trailing whitespace في الاختبار يخصان سطرين توثيقيين قديمين داخل
نسخة الإنتاج المحفوظة؛ لا يؤثران في إعادة التركيب.

## نتيجة المصالحة

### كل source paths

| القياس | العدد |
|---|---:|
| live total | 674 |
| local total | 682 |
| common | 669 |
| common content different | 23 |
| mode different | 0 |
| live-only | 5 |
| local-only | 13 |

الخمسة live-only هي تعليمات يوليو القديمة التي نُقلت محليًا إلى
`docs/archive/2026-07-execution/`. الملفات المحلية-only هي التوثيق الحي
والأرشيف الجديد وhandoffs وشاشة طوارئ اختيار الفرع.

### مسارات تغييرات الإنتاج

- 88 مسارًا متغيرًا/جديدًا على الإنتاج.
- 77 متطابقة حرفيًا مع المحلي.
- 9 مختلفة لأن المحلي يحتوي إصلاحات أحدث ومراجعة نهائية.
- 2 missing في المسار القديم لأنهما نُقلا إلى الأرشيف.

الفروق البرمجية راجعت: auth bootstrap objects، permission keys، branch
directory validation، route/action gates، offline queue identity، Vue ref
payloads، Night Audit endpoint، WebSocket branch value، وmigration downgrade
غير الهدام. مفاتيح الصلاحيات ومسار Night Audit طابقت عقد الـBackend.

## القرار

- SRC-01: COMPLETE.
- SRC-02: COMPLETE.
- لا production-only source مجهول.
- REL-01 أُغلق بعد final gate: code commit `6c9f09e` ثم commit توثيق منفصل.
- push/deploy يظلان ممنوعين حتى DR-01: نسخة بيانات خارج الخادم أو provider
  snapshot قابلة للاسترجاع.
- ملف المستخدم `scripts/wait-dns-then-switch.sh` متطابق ولم يُعدّل أو يُشغّل.
