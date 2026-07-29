# الخطة التنفيذية النهائية الحية — El Kheima Resort OS

**آخر تحديث مثبت:** 2026-07-29
**المالك:** Mohamed
**قائد التنفيذ والمراجع النهائي:** Codex
**الحالة:** IP-only يعمل؛ النشر التالي متوقف لحماية ومصالحة مصدر الإنتاج

## 1. القرارات غير القابلة للالتباس

1. الخيمة تعمل بفرع تشغيلي واحد فقط حاليًا.
2. لا Branch Switcher ظاهر؛ عضوية الفرع والصلاحيات تُفرض fail-closed.
3. أصل التشغيل العام هو `https://191.218.161.133`.
4. لا DNS أو domain switch بلا قرار صريح جديد من Mohamed.
5. لا `git pull` أو reset أو rsync أو rebuild فوق الإنتاج قبل حفظ exact source.
6. لا أسرار في Git أو logs أو handoffs، ولا قراءة لقيم `backend/.env.prod`.
7. لا `app.seed` ولا بيانات demo أو master data غير معتمدة.
8. كل نشر يحتاج backup، rollback، health check، وإثبات image/source digest.
9. أي تعليمات تحت `docs/archive/` تاريخية وممنوع تنفيذها.
10. `scripts/wait-dns-then-switch.sh` خارج النطاق الحالي ولا يُلمس.

## 2. خط الأساس المثبت

### الكود المحلي

- branch: `claude/CX-02C-frontend-auth-bootstrap`
- reviewed code commit: `6c9f09e`
- frontend auth/bootstrap/permissions/route gates: مكتملة محليًا.
- single-branch UX: لا selector ظاهر، ومسار اختيار الفرع للطوارئ fail-closed.
- offline queue: مربوط بالمستخدم والفرع والموديول.
- Alembic head: `88d1c505a9dc`.
- full backend: 100% بصفر failure.
- targeted backend: 63 passed.
- frontend: 93/93.
- type-check/build/agent-check/git diff check: ناجحة.

### الإنتاج

- SSH بالمفتاح كمستخدم `resortos` مع sudo وDocker.
- root login وpassword auth مغلقان؛ UFW وFail2ban يعملان.
- 8 حاويات تعمل؛ Backend healthy و`/health` = 200 وصفر restart.
- PostgreSQL/Backend/Redis host ports loopback-only.
- backup timer ناجح، وأحدث dump يمر `pg_restore --list`.
- Certbot IP renewal dry-run ناجح، والمؤقت يعمل كل 12 ساعة.
- Hostinger provider snapshots/backups: صفر وقت الفحص.
- Git على الإنتاج: `0a13c97` مع 79 tracked modified وملفات untracked.
- الصور الحالية بُنيت من الشجرة غير النظيفة؛ SHA وحده لا يصف الإصدار الحي.

## 3. حالة البوابات

| Gate | الحالة | شرط الإغلاق |
|---|---|---|
| Gate 0 — baseline | COMPLETE | الأدلة الحالية خضراء |
| Gate 1 — auth/permissions/branch | CODE COMPLETE — LOCAL | مصالحة المصدر ثم deploy/UAT |
| Gate 2 — QR/PWA/public | PARTIAL | device UAT والعقد العام النهائي |
| Gate 3 — chat/consent/truth | DEPLOYED CONTAINMENT | governance وapproved facts قبل التفعيل |
| Gate 4 — content/SEO | PARTIAL | بيانات مالك موثقة |
| Gate 5 — production data | BLOCKED ON INPUT | master data واعتماد مالي |
| Gate 6 — VPS hardening | COMPLETE + VERIFIED | مراجعة دورية فقط |
| Gate 7 — deploy/backup/monitoring | IN PROGRESS | source reconciliation + offsite + alerts |
| Gate 8 — TLS/UAT | PARTIAL | UAT جهاز/عمل وتشغيل |
| Gate 9 — cutover | PAUSED — IP-ONLY | قرار مالك جديد فقط |

## 4. ترتيب التنفيذ الحالي

### P0-01 — حفظ ومصالحة exact source للإنتاج

**الحالة:** COMPLETE — 2026-07-29

- حُفظ manifest وGit bundle وbinary patch وuntracked tar وDocker metadata.
- النسخة موجودة على الـVPS وخارجه تحت
  `/home/wego/backups/resort-os/production-source/`.
- SHA-256 الخارجي:
  `71b7bb408b2e0be822d4f2e212fa26c37f32f8761b770d0585efd37e76ed50b3`.
- أُعيد تركيب المصدر في clone مؤقت وتطابق patch وuntracked files حرفيًا.
- المقارنة الشاملة: live=674، local=682، common=669، content differences=23،
  mode differences=0، live-only=5 مؤرشفة، local-only=13 مقصودة.
- 77/88 من مسارات تغييرات الإنتاج متطابقة محليًا؛ لا يوجد source مجهول.

**القبول:** PASSED — يمكن إعادة بناء الإصدار الحي من مصدر محفوظ.

### P0-02 — نقطة تراجع خارج الخادم

**الحالة:** COMPLETE — encrypted off-server DB + isolated restore drill

- أحدث dump محفوظ كـGPG/AES-256 خارج الـVPS دون plaintext محلي.
- source/decrypted SHA-256 متطابقان، وencrypted artifact checksum محفوظ.
- restore كامل نجح في قاعدة مؤقتة: 135 جدولًا وAlembic `c4d8e2f6a901`.
- حُذفت قاعدة الاختبار وتأكدت صحة حاويات/DB/Redis/HTTP بعدها.
- provider snapshot ونسخة منفصلة للمفتاح يظلان تحسينين دفاعيين.

**القبول:** PASSED للحد الأدنى خارج الخادم؛ RPO الحالي يقارب 24 ساعة.

### P0-03 — تثبيت المصدر المحلي

**الحالة:** COMPLETE — code `6c9f09e` + documentation consolidation commit

- روجع diff النهائي واستُبعدت الأسرار وملف المستخدم الخاص بالـDNS.
- حزمة الكود ثُبتت في commit واضح من gates خضراء.
- التوثيق الحي والأرشيف يُثبتان في commit منفصل.
- push إجراء منفصل بعد إثبات نقطة التراجع.

### P0-04 — نشر محكوم

**الحالة:** IN PROGRESS — preflight فقط؛ لا deploy قبل نتيجة صريحة

- pre-deploy backup.
- build من commit مثبت مع image digests.
- migrations expand-safe.
- نشر أقل مجموعة خدمات لازمة.
- health/smoke/permissions/branch checks.
- rollback فوري عند فشل شرط قبول.

### P0-05 — UAT وGo/No-Go

**الحالة:** PENDING

- جهاز وهاتف حقيقيان، عربي/إنجليزي، QR، انقطاع شبكة، logout/login.
- استقبال/غرف/housekeeping/night audit/POS/guest alerts حسب الأدوار.
- اعتماد ممثل التشغيل والمالية والمالك.
- تسجيل defects وقرار Go/No-Go مؤرخ.

### P1 — البيانات والمراقبة

- استيراد master data عبر dry-run/validation/audit فقط.
- monitoring للحاويات، HTTP، backup، TLS، disk/memory، وأخطاء التطبيق.
- لا تفعيل Chatbot أو analytics أو facts عامة قبل governance واعتماد المحتوى.

## 5. قواعد التراجع

- لا حذف schema أو أعمدة في نفس إصدار توسيع/تحويل البيانات.
- لا rollback migration يصغّر أعمدة ciphertext.
- احتفظ بصورة الإصدار السابق ونسخة DB قبل النشر.
- لا تستخدم `git reset --hard` أو حذف worktree كوسيلة rollback إنتاجية.
- rollback يُختبر قبل Go/No-Go ويُوثق بالوقت والنتيجة.

## 6. الأدلة الحالية

- لوحة التنفيذ: `docs/agent-workflow/EL_KHEIMA_EXECUTION_BOARD.md`
- تدقيق VPS: `docs/agent-workflow/handoffs/2026-07-29_VPS-03_codex_handoff.md`
- حالة المشروع: `PROJECT_STATUS.md`
- ملخص المالك: `wagdy.md`
- التاريخ القديم: `docs/archive/2026-07-execution/`
