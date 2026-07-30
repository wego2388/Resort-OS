# لوحة التنفيذ الحية — El Kheima

**آخر تحديث:** 2026-07-30 بعد تشغيل الدومينات
**المالك:** Mohamed
**قائد التنفيذ والمراجع النهائي:** Codex
**المرحلة الحالية:** UAT-01 + DATA-02 + OPS-01
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
- ملف `scripts/wait-dns-then-switch.sh` مملوك للمستخدم ولا يُلمس.

## المهمة الجارية

| الحزمة | الحالة | النتيجة المطلوبة | المانع |
|---|---|---|---|
| SRC-01 — exact-source preservation | COMPLETE | أرشيفات وchecksums قابلة لإعادة البناء | — |
| REL-02 — controlled immutable deploy | COMPLETE | `05ee627` فعال على كل خدمات التطبيق | — |
| DATA-01-DEMO — realistic synthetic data | COMPLETE | بيانات مترابطة وآمنة وقابلة للتكرار | — |
| CHAT-01 — live chatbot | COMPLETE | disclosure + Gemini E2E من الدومين | — |
| DNS-01 — domain/TLS cutover | COMPLETE | DNS + SAN cert + edge + rollback | — |
| DOC-OPS — management/staff training | COMPLETE | دليل عربي للأدوار ودورات العمل وUAT | — |
| ACC-01 — named staff accounts | PENDING | حساب شخصي لكل موظف + super-admin احتياطي | قائمة أسماء/بريد/أدوار معتمدة |
| OPS-01 — burn-in and alerting | BASELINE COMPLETE | مراقبة مستمرة + إرسال خارجي | اختيار قناة التنبيه |
| UAT-01 — operational acceptance | PENDING | جهاز/دور/لغة/شبكة/مال | ممثلو التشغيل والمالية |
| DATA-02 — approved real master data | PENDING REVIEW | استبدال demo بما تعتمده العمليات | المالك والتشغيل |

## ما اكتمل

- [x] مراجعة auth والصلاحيات وعزل الفرع وOffline Queue.
- [x] full backend 2217 collected بصفر failure.
- [x] 63 targeted backend و93/93 frontend.
- [x] type-check/build/agent-check/Alembic single-head/diff-check.
- [x] SSH key-only، sudo/Docker، UFW/Fail2ban والـloopback listeners.
- [x] حفظ exact production source وإعادة تركيبه، ونسخة DB مشفرة مع restore.
- [x] importer إنتاجي آمن وidempotent ببيانات مخزون وموردين ومطعم وغرف
  وبقية الموديولات.
- [x] safety counts ثابتة؛ لا مستخدمين أو مدفوعات أو حجوزات أو رواتب demo.
- [x] Chatbot live E2E بالعربية.
- [x] rollback للصور وDB والشهادات قبل domain cutover.
- [x] إصلاح backup retention واختبار nested protected rollback directory.
- [x] Resort release `05ee627` وMarketing release `e5e122a` مع SHA-256.
- [x] Hostinger DNS snapshot `167902017`.
- [x] `@ A` و`app A` إلى `191.218.161.133`، و`www CNAME` محفوظ.
- [x] شهادة SAN للدومينات الثلاثة وتجديد dry-run ناجح.
- [x] Nginx domain edge وHTTP redirects وHSTS canary.
- [x] DNS authoritative + Cloudflare + Google + Quad9 جميعها على VPS.
- [x] apex/www/app وhealth يعيدون 200 من خارج الخادم.
- [x] Marketing bundle وHTML وrobots وsitemap بلا أي IP قديم.
- [x] خدمات التطبيق الست موحدة على `/opt/resort-os-releases/05ee627`
  وكلها restarts=0.
- [x] المنافذ العامة 80/443 فقط؛ 8443 القديم أُغلق.
- [x] ملفات المصدر القديمة على VPS محفوظة وغير مستخدمة كمصدر للنشر.
- [x] دليل عربي شامل للإدارة وتدريب الموظفين مع الحسابات والأدوار والمالية
  والتكلفة والمخزون والموردين وHR والتايم شير وCRM وخدمة العملاء.
- [x] مراجعة دليل السوبر أدمن وتصحيح إنشاء الحساب و2FA وStep-Up والطوارئ.

## حالة الإنتاج المثبتة

| البند | النتيجة |
|---|---|
| Host/IP | `resort-os-prod` / `191.218.161.133` |
| Public site | `https://elkheima.com` و`https://www.elkheima.com` |
| Staff app | `https://app.elkheima.com` |
| Containers | 8 Running؛ healthchecks ناجحة |
| Ports | 5436/6381/8005 loopback-only؛ 80/443 public |
| Resort release | `/opt/resort-os-current -> .../05ee627` |
| Marketing release | `/opt/elkheima-marketing-current -> .../e5e122a` |
| Database | Alembic `88d1c505a9dc`؛ marker واحد؛ safety counts ثابتة |
| TLS | Let's Encrypt SAN حتى `2026-10-28 02:21:34 UTC` |
| DNS rollback | Hostinger snapshot `167902017` |
| Chatbot | Active؛ live Gemini E2E passed من `elkheima.com` |
| Accounts | `super_admin` واحد نشط؛ صفر حسابات موظفين |
| Monitoring | health/backup/certbot timers مفعلة |
| Legacy source | محفوظ وغير مستخدم كمصدر للحاويات |

## أدلة التشغيل

- Resort release archive:
  `/var/backups/resort-os/source-releases/05ee627.tar.gz`
- Resort SHA-256:
  `d8354ec5b48e69a284dc6a6194967ca788f290fe508ba4fd30af0c5bf6946c5b`
- Marketing release archive:
  `/var/backups/resort-os/marketing-source-releases/e5e122a.tar.gz`
- Marketing SHA-256:
  `357d28e5a4fab05650f19ba0b9f5f82ea6f10e13e29633d47cad388b45e2aaa2`
- Domain rollback directory:
  `/var/backups/resort-os-domain-cutover-aed94a0`
- DNS rollback snapshot: `167902017`

## آخر تسليم

`docs/agent-workflow/handoffs/2026-07-30_DNS-01_codex_handoff.md`

## التحديث التالي المطلوب

اعتمد قائمة الموظفين (الاسم والبريد وسجل HR والدور) وأنشئ حساباتهم الشخصية،
ثم وزّع `docs/STAFF_APP_GUIDE_AR.md` على رؤساء الأقسام ونفّذ سيناريوهات
UAT بالأجهزة والأدوار. راجع بيانات العرض واعتمد بدائلها الحقيقية، واختر
قناة alerts خارجية. بعد burn-in وretest، يسجل Mohamed قرار Go/No-Go
التشغيلي المؤرخ.
