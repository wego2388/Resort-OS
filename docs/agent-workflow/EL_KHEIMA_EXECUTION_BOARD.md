# لوحة التنفيذ الحية — El Kheima

**آخر تحديث:** 2026-08-08 — CREDIT-0005 منشور ومتحقق على الإنتاج
**المالك:** Mohamed
**قائد التنفيذ والمراجع النهائي:** Codex
**المرحلة الحالية:** ACC-01 roster + UAT-01 + production burn-in
**قرار الإطلاق:** CREDIT-0005 DEPLOYED؛ قرار Go/No-Go التشغيلي العام ما زال
مرتبطًا بالـUAT والبيانات الحقيقية

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
| MKT-03 — locale-aware nav links + View Transitions race fix | COMPLETE | `0b0321f` فعال؛ صفر InvalidStateError، محتوى يظهر فورًا بدون ريفريش | — |
| POS-02 — cross-outlet order support + refund revenue-account fix | COMPLETE | `ddfbaaa` فعال؛ صنف من منفذ تاني على نفس الفاتورة + مرتجع يعكس الحساب الصح | — |
| HR-01 — income tax bracket calculation fix | COMPLETE | `4a0a777` فعال؛ حساب الشرائح الضريبية بيعامل الفجوة القانونية كعرض بس | — |
| CRM-01 — loyalty redeem row-lock fix | COMPLETE | `8597535` فعال؛ قفل صف حساب النقاط يمنع خصم استرداد مزدوج متزامن | — |
| MNT-01 — work-order completion bypass + asset-release-on-cancel fix | COMPLETE | `b1db886` فعال؛ إغلاق "مكتمل" لازم /complete المخصص، والإلغاء بيحرر الأصل زي الإكمال | — |
| ANL-01 — guest review submit input validation | COMPLETE | `0d55717` فعال؛ endpoint عام بدون auth بقى محمي بـschema بدل dict خام | — |
| LSE-01 — cash-log rent collection blocked on terminated/expired lease | COMPLETE | `4ca10c1` فعال؛ التسوية الكاش اليومية بقت تفرض نفس فحص حالة العقد زي التحصيل العادي | — |
| HUB-01 — confirm_booking dead-code UnboundLocalError fix | COMPLETE | `5b02010` فعال؛ حذف كود مكرر كان بيسبب خطأ صامت مضلّل عند عدم توفر غرف | — |
| MKT-04 — guest survey form maxlength guards | COMPLETE | `4fba5b6` فعال (Marketing)؛ حدود العميل تطابق GuestReviewSubmitRequest الجديدة | — |
| MKT-05 — remaining site pages: idempotency-on-failure + PUBLIC_TRUTH gate leaks + locale routing | COMPLETE | `53bf7a3` فعال (Marketing)؛ 7 فورمات + 4 تسريبات بوابة + رابط Products.vue | — |
| MKT-06 — Arabic-only horizontal scroll on /contact (RTL honeypot offset bug) | COMPLETE | `1371975` فعال (Marketing)؛ sr-only بدل offset فيزيائي ضخم | — |
| REL-06 — HR/admin/Timeshare audit batch (23 commits، تفويض مباشر من Mohamed خارج دورة Codex) | COMPLETE | `821a718` فعال؛ VAT/service-charge حقيقي، جلسات إدارية، بوابة تايم شير كاملة + تنبيهات واتساب، إصلاح fail-closed لـTIMESHARE_PORTAL_TOKEN_SECRET | — |
| REL-07 — Arabic PDF invoice fix + real blog + marketing-site console-error sweep (8 commits + Marketing، تفويض مباشر من Mohamed خارج دورة Codex) | COMPLETE | `5df8191` فعال (Resort) + `79130a6` فعال (Marketing)؛ خط عربي/لوجو للفواتير، `GET /hub/blog/posts/{slug}` + 6 مقالات حقيقية، حذف نداءات API ميتة + إصلاح باج انتقال صفحات + كارت وصف بدل زر طلب وهمي | — |
| CREDIT-0005 — personal customer/employee credit accounts | COMPLETE / DEPLOYED | `1d77e7b` فعال؛ Alembic `c9d4e5f6a7b8`؛ GL 1160 + immutable ledger + Dining/Beach + Staff/Owner UI؛ health/smoke/log gates ناجحة | — |
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
- [x] CREDIT-0005: DB backup + rollback images، build من exact source، migration
  `c9d4e5f6a7b8`، استبدال تدريجي، 4/4 domains HTTP 200، صفر restarts/log errors.
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
| Resort release | `/opt/resort-os-current -> .../5df8191` |
| Marketing release | `/opt/elkheima-marketing-current -> .../79130a6` |
| Database | Alembic `7b4d81dc08ee`؛ marker واحد؛ safety counts ثابتة |
| TLS | Let's Encrypt SAN حتى `2026-10-28 02:21:34 UTC` |
| DNS rollback | Hostinger snapshot `167902017` |
| Chatbot | Active؛ live Gemini E2E passed من `elkheima.com` |
| Accounts | `super_admin` واحد، عضوية فعالة واحدة؛ صفر سجلات/حسابات موظفين |
| Monitoring | health/backup/certbot timers مفعلة |
| Legacy source | محفوظ وغير مستخدم كمصدر للحاويات |

## أدلة التشغيل

- Resort release archive:
  `/var/backups/resort-os/source-releases/5df8191.tar.gz`
- Resort SHA-256:
  `df209816d2ac9547d42cfc64c45c007a939d7d90f2a586832d30d1fde7e02963`
- Rollback image manifest:
  `/var/backups/resort-os/source-releases/5df8191-rollback-images.txt`
- Pre-deploy DB (`5df8191`):
  `/opt/resort-os-releases/5df8191/backups/resort_os_20260804_204745.dump`
- Marketing release archive:
  `/var/backups/resort-os/marketing-source-releases/79130a6.tar.gz`
- Marketing SHA-256:
  `f8e454beb95a48ac8c72ec8705c36ca50948289f2e690587a9bb629ee4fe5a9f`
- Domain rollback directory:
  `/var/backups/resort-os-domain-cutover-aed94a0`
- DNS rollback snapshot: `167902017`

## آخر تسليم

`docs/agent-workflow/handoffs/2026-08-08_CREDIT-0005_codex_handoff.md`

## التحديث التالي المطلوب

اعتمد قائمة الموظفين (الاسم والبريد والدور والمدير). ينشئ HR سجل الموظف
أولًا ثم ينشئ السوبر أدمن حسابه الشخصي من مركز الإدارة. يُنشأ حساب
`super_admin` الاحتياطي عبر bootstrap من الطرفية فقط،
ثم وزّع `manual/02-دليل-الموظفين-والتدريب.md` على رؤساء الأقسام ونفّذ سيناريوهات
UAT بالأجهزة والأدوار. راجع بيانات العرض واعتمد بدائلها الحقيقية، واختر
قناة alerts خارجية. بعد burn-in وretest، يسجل Mohamed قرار Go/No-Go
التشغيلي المؤرخ.
