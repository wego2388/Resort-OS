# لوحة التنفيذ الحية — El Kheima

**آخر تحديث:** 2026-07-31 بعد نشر إصلاح تبديل منافذ الـPOS
**المالك:** Mohamed
**قائد التنفيذ والمراجع النهائي:** Codex
**المرحلة الحالية:** ACC-01 roster + UAT-01 + DATA-02 + OPS-01
**قرار الإطلاق:** domain production فعال؛ Go/No-Go التشغيلي ينتظر UAT

> هذه اللوحة تعرض العمل الحالي فقط. التفاصيل في
> `docs/audits/EL_KHEIMA_FINAL_EXECUTION_PLAN_AR.md`. أي لوحة قديمة تحت
> `docs/archive/` تاريخية وممنوع التنفيذ منها.

## قرارات سارية

- فرع تشغيلي واحد للخيمة؛ لا Branch Switcher ظاهر.
- العزل والصلاحيات fail-closed في Backend والواجهة والطابور غير المتصل.
- Codex ينفذ ويراجع نهائيًا؛ Mohamed يعتمد القرارات التجارية والبيانات
  الحقيقية وGo/No-Go.
- الإنتاج الرسمي:
  `elkheima.com` + `www.elkheima.com` للموقع،
  و`app.elkheima.com` للموظفين.
- أي تغيير إنتاج جديد يحتاج backup وrollback وhealth evidence.
- أي تغيير DNS لاحق محدد ومراجع؛ لا Reset DNS ولا AAAA دون IPv6.

## المهمة الجارية

| الحزمة | الحالة | النتيجة المطلوبة | المانع |
|---|---|---|---|
| SRC-01 — exact-source preservation | COMPLETE | أرشيفات وchecksums قابلة لإعادة البناء | — |
| REL-04 — staff control-plane deploy | COMPLETE | `679f76e` فعال على خدمات Resort المتغيرة | — |
| REL-05 — multi-outlet POS fix | COMPLETE | `a3e8abb` فعال على تطبيق الموظفين والـedge | — |
| DATA-01-DEMO — realistic synthetic data | COMPLETE | بيانات مترابطة وآمنة وقابلة للتكرار | — |
| CHAT-01 — live chatbot | COMPLETE | disclosure + Gemini E2E من الدومين | — |
| DNS-01 — domain/TLS cutover | COMPLETE | DNS + SAN cert + edge + rollback | — |
| DOC-OPS — management/staff training | COMPLETE | دليل عربي للأدوار ودورات العمل وUAT | — |
| MKT-02 — Timeshare + multilingual Marketing | COMPLETE | Blue Bay + CRM inquiry + reviewed images/i18n | — |
| ACC-01 — employee/account workflow | DEPLOYED؛ ACCOUNTS PENDING | HR record ثم حساب شخصي من مركز السوبر أدمن + super-admin احتياطي | قائمة أسماء/بريد/أدوار معتمدة |
| OPS-01 — burn-in and alerting | BASELINE COMPLETE | مراقبة مستمرة + إرسال خارجي | اختيار قناة التنبيه |
| UAT-01 — operational acceptance | PENDING | جهاز/دور/لغة/شبكة/مال | ممثلو التشغيل والمالية |
| DATA-02 — approved real master data | PENDING REVIEW | استبدال demo بما تعتمده العمليات | المالك والتشغيل |

## ما اكتمل

- [x] مراجعة auth والصلاحيات وعزل الفرع وOffline Queue.
- [x] full backend: 2181 passed و40 skipped من 2221 collected، بصفر failure.
- [x] onboarding/HR/auth focused backend: 228 passed و1 skipped؛
  frontend 95/95.
- [x] type-check/build/agent-check/Alembic single-head/diff-check.
- [x] SSH key-only، sudo/Docker، UFW/Fail2ban والـloopback listeners.
- [x] حفظ exact production source وإعادة تركيبه، ونسخة DB مشفرة مع restore.
- [x] importer إنتاجي آمن وidempotent ببيانات مخزون وموردين ومطعم وغرف
  وبقية الموديولات.
- [x] safety counts ثابتة؛ لا مستخدمين أو مدفوعات أو حجوزات أو رواتب demo.
- [x] Chatbot live E2E بالعربية.
- [x] rollback للصور وDB والشهادات قبل domain cutover.
- [x] إصلاح backup retention واختبار nested protected rollback directory.
- [x] Resort release `a3e8abb` وMarketing release `16f8f2c` مع SHA-256.
- [x] Hostinger DNS snapshot `167902017`.
- [x] `@ A` و`app A` إلى `191.218.161.133`، و`www CNAME` محفوظ.
- [x] شهادة SAN للدومينات الثلاثة وتجديد dry-run ناجح.
- [x] Nginx domain edge وHTTP redirects وHSTS canary.
- [x] DNS authoritative + Cloudflare + Google + Quad9 جميعها على VPS.
- [x] apex/www/app وhealth يعيدون 200 من خارج الخادم.
- [x] Marketing bundle وHTML وrobots وsitemap بلا أي IP قديم.
- [x] تطبيق الموظفين والـedge على `/opt/resort-os-releases/a3e8abb`؛
  Backend وCelery بقيا على `679f76e`، وMarketing المستقل لم يُعد بناؤه؛
  الحاويات الثماني restarts=0.
- [x] تبديل المنفذ داخل طلب POS قائم لا يلغي الطلب؛ Bundle الإنتاج طابق
  البناء المحلي وhealth gate نجح.
- [x] المنافذ العامة 80/443 فقط؛ 8443 القديم أُغلق.
- [x] ملفات المصدر القديمة على VPS محفوظة وغير مستخدمة كمصدر للنشر.
- [x] دليل عربي شامل للإدارة وتدريب الموظفين مع الحسابات والأدوار والمالية
  والتكلفة والمخزون والموردين وHR والتايم شير وCRM وخدمة العملاء.
- [x] مراجعة دليل السوبر أدمن وتصحيح إنشاء الحساب و2FA وStep-Up والطوارئ.
- [x] دورة HR record ثم Super Admin account منشورة مع عضوية فرع تلقائية
  وStep-Up وAudit وعزل fail-closed.
- [x] دمج المستخدمين والصلاحيات في مركز إدارة واحد وتنظيم sidebar حسب
  الموديولات وتحسين عرض الهاتف.
- [x] صفحة Timeshare بأربع لغات، Blue Bay كجهة إدارة، ونموذج CRM محكوم
  بالموافقة دون أسعار أو وعود تعاقدية غير معتمدة.

## حالة الإنتاج المثبتة

| البند | النتيجة |
|---|---|
| Host/IP | `resort-os-prod` / `191.218.161.133` |
| Public site | `https://elkheima.com` و`https://www.elkheima.com` |
| Staff app | `https://app.elkheima.com` |
| Containers | 8 Running؛ healthchecks ناجحة |
| Ports | 5436/6381/8005 loopback-only؛ 80/443 public |
| Resort release | `/opt/resort-os-current -> .../a3e8abb` |
| Marketing release | `/opt/elkheima-marketing-current -> .../16f8f2c` |
| Database | Alembic `88d1c505a9dc`؛ marker واحد؛ safety counts ثابتة |
| TLS | Let's Encrypt SAN حتى `2026-10-28 02:21:34 UTC` |
| DNS rollback | Hostinger snapshot `167902017` |
| Chatbot | Active؛ live Gemini E2E passed من `elkheima.com` |
| Accounts | `super_admin` واحد، عضوية فعالة واحدة؛ صفر سجلات/حسابات موظفين |
| Monitoring | health/backup/certbot timers مفعلة |
| Legacy source | محفوظ وغير مستخدم كمصدر للحاويات |

## أدلة التشغيل

- Resort release archive:
  `/var/backups/resort-os/source-releases/a3e8abb.tar.gz`
- Resort SHA-256:
  `2ff370284727ae57688c4efda9dad22db2729abf45fbbfe3dc276e78d7388bad`
- Rollback image manifest:
  `/var/backups/resort-os/source-releases/a3e8abb-rollback-images.txt`
- Pre-cutover DB:
  `/var/backups/resort-os/database/resort_os_20260730_062529.dump`
- Marketing release archive:
  `/var/backups/resort-os/marketing-source-releases/16f8f2c.tar.gz`
- Marketing SHA-256:
  `ba3d8d5c25c8487fb75906ce17ca3ffe8c0df9f0a087c0afefb478c9129cf7a9`
- Domain rollback directory:
  `/var/backups/resort-os-domain-cutover-aed94a0`
- DNS rollback snapshot: `167902017`

## آخر تسليم

`docs/agent-workflow/handoffs/2026-07-31_POS-01_REL-05_codex_handoff.md`

## التحديث التالي المطلوب

اعتمد قائمة الموظفين (الاسم والبريد والدور والمدير). ينشئ HR سجل الموظف
أولًا ثم ينشئ السوبر أدمن حسابه الشخصي من مركز الإدارة. يُنشأ حساب
`super_admin` الاحتياطي عبر bootstrap من الطرفية فقط،
ثم وزّع `docs/STAFF_APP_GUIDE_AR.md` على رؤساء الأقسام ونفّذ سيناريوهات
UAT بالأجهزة والأدوار. راجع بيانات العرض واعتمد بدائلها الحقيقية، واختر
قناة alerts خارجية. بعد burn-in وretest، يسجل Mohamed قرار Go/No-Go
التشغيلي المؤرخ.
