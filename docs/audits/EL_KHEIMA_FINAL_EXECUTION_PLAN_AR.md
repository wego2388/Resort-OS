# الخطة التنفيذية النهائية الحية — El Kheima Resort OS

**آخر تحديث مثبت:** 2026-07-29
**المالك:** Mohamed
**قائد التنفيذ والمراجع النهائي:** Codex
**الحالة:** REL-02 منشور وhealthy؛ المرحلة الحالية UAT/monitoring قبل Go/No-Go

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
- release source commit: `ac7764f`؛ إصلاحات الكود الأساسية في `6c9f09e`.
- الفرع مدفوع إلى `origin/claude/CX-02C-frontend-auth-bootstrap`؛ `main` لم يتغير.
- frontend auth/bootstrap/permissions/route gates: مكتملة ومنشورة.
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
- release الفعال: `/opt/resort-os-releases/ac7764f`.
- 8 حاويات تعمل؛ Backend/Celery/El Kheima healthy و`/health` = 200 وصفر restart.
- PostgreSQL/Backend/Redis host ports loopback-only.
- staff HTTPS على 443 والموقع التسويقي على 8443 يعيدان 200 من خارج الخادم.
- backup timer ناجح، وpre-deploy dump ونقطة rollback للصور محفوظان.
- Certbot IP renewal dry-run ناجح، والمؤقت يعمل كل 12 ساعة.
- Hostinger provider snapshots/backups: صفر وقت الفحص.
- مجلد Git القديم `0a13c97` غير النظيف محفوظ لكنه لم يعد مصدر الحاويات المحدثة.
- الصور الفعالة مرتبطة بـcommit وdigests موثقة في تسليم REL-02.

## 3. حالة البوابات

| Gate | الحالة | شرط الإغلاق |
|---|---|---|
| Gate 0 — baseline | COMPLETE | الأدلة الحالية خضراء |
| Gate 1 — auth/permissions/branch | DEPLOYED — UAT PENDING | قبول الأدوار على جهاز فعلي |
| Gate 2 — QR/PWA/public | PARTIAL | device UAT والعقد العام النهائي |
| Gate 3 — chat/consent/truth | DEPLOYED CONTAINMENT | governance وapproved facts قبل التفعيل |
| Gate 4 — content/SEO | PARTIAL | بيانات مالك موثقة |
| Gate 5 — production data | BLOCKED ON INPUT | master data واعتماد مالي |
| Gate 6 — VPS hardening | COMPLETE + VERIFIED | مراجعة دورية فقط |
| Gate 7 — deploy/backup/monitoring | DEPLOY + DR COMPLETE | alerts وburn-in |
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

**الحالة:** COMPLETE — code `6c9f09e` + docs `56e7219` + DR `ac7764f`

- روجع diff النهائي واستُبعدت الأسرار وملف المستخدم الخاص بالـDNS.
- حزمة الكود ثُبتت في commit واضح من gates خضراء.
- التوثيق الحي والأرشيف ثُبتا في commits منفصلة.
- الفرع دُفع بعد إثبات نقطة التراجع؛ `origin/main` لم يُمس.

### P0-04 — نشر محكوم

**الحالة:** COMPLETE — 2026-07-29

- بُني commit `ac7764f` داخل release immutable بعد نجاح preflight.
- حُفظ dump قبل النشر وrollback tags للصور القديمة.
- Alembic عند `88d1c505a9dc`؛ أمر upgrade نجح بلا تغيير إضافي.
- نُشرت backend ثم Celery ثم El Kheima، وأُعيد إنشاء Nginx لإعادة الربط.
- الصور الأربع الفعالة تطابق digests المسجلة، وكلها restarts=0.
- HTTPS 443/8443 وhealth وDB/Redis وcounts والسجلات اجتازت smoke checks.
- لم تُستبدل PostgreSQL أو Redis أو marketing site، ولم يُستخدم مجلد Git
  القديم كمصدر بناء.

**القبول:** PASSED — لا يوجد سبب تقني للـrollback وقت التحقق.

### P0-05 — UAT وGo/No-Go

**الحالة:** PENDING

- جهاز وهاتف حقيقيان، عربي/إنجليزي، QR، انقطاع شبكة، logout/login.
- استقبال/غرف/housekeeping/night audit/POS/guest alerts حسب الأدوار.
- فترة burn-in مع alerts للـHTTP/containers/backup/TLS/disk.
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
- تسليم النشر: `docs/agent-workflow/handoffs/2026-07-29_REL-02_codex_handoff.md`
- حالة المشروع: `PROJECT_STATUS.md`
- ملخص المالك: `wagdy.md`
- التاريخ القديم: `docs/archive/2026-07-execution/`
