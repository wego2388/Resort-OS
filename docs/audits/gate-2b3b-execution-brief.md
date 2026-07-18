# Gate 2B3B — Authentication Audit & Session Defense

**الحالة:** جاهزة للتنفيذ على الفرع
`gate-2b3b-auth-audit-session-defense` فوق Gate 2B3A المُعتمَدة.

**طريقة العمل:** Claude ينفّذ الحزمة كاملة بثلاث شرائح داخلية مترابطة، ثم
يشغّل التحقق الكامل ويتوقف بلا commit أو push حتى يراجع Codex الناتج مرة
واحدة في النهاية. لا يتوقف بعد تقرير القراءة إلا إذا ظهر blocker حقيقي من
قواعد المشروع.

## لماذا هذه هي الخطوة التالية؟

Gate 2B1 أمّنت تغيير كلمة السر ودورة refresh الأساسية، وGate 2B2 أمّنت
bootstrap وTOTP والاسترداد، وGate 2B3A أضافت step-up أحادي الاستخدام
لعمليات التحكم الحساسة. المتبقي داخل حدود الهوية والجلسات الآن:

1. أحداث المصادقة الحساسة ليست كلها قابلة للمراجعة في `AuditLog` الموحّد.
2. refresh token المستهلَك يُحذف، لذلك لا يمكن اكتشاف إعادة استخدامه لاحقًا
   أو إبطال السلسلة التي خرجت منه.
3. المستخدم لا يستطيع رؤية جلساته الفعلية أو إلغاء جلسة مفقودة من واجهة
   الأمان.

حل الثلاثة معًا يحافظ على حدود واضحة: سجل أمني واحد، دورة جلسة واحدة،
وواجهة self-service واحدة. لا نخلط بهذه الدفعة typed settings أو user→branch
أو step-up العمليات المالية.

## قبل التعديل

اقرأ بالكامل ما يرتبط بالنطاق، وبالأخص:

- `CLAUDE.md` و`AGENTS.md` و`wagdy.md`.
- `docs/audits/gate-2b1-auth-session-lifecycle.md`.
- `docs/audits/gate-2b2-totp-bootstrap-recovery.md`.
- `docs/audits/gate-2b3a-step-up-control-plane.md`.
- auth models/repository/service/router/security/rate-limit.
- `AuditLog` model/schema/service/API وأي trusted-client-IP helper موجود.
- Profile/Security frontend، auth store، التصميم والترجمة الحالية.
- اختبارات auth وPostgreSQL concurrency والمigrations الحالية.

سجّل baseline مختصرًا داخل التقرير النهائي، ثم نفّذ ولا تتوقف عند التخطيط.

## الشريحة A — Unified, bounded, secret-free security audit

استخدم جدول `AuditLog` الموجود فقط. لا تنشئ جدول أحداث موازٍ ولا تضع أسرارًا
في structured logs أو audit payloads.

أنشئ مسجلًا مركزيًا صغيرًا وواضحًا لأحداث أمان المصادقة يدعم عند الملاءمة:

- actor/user id عندما تكون الهوية معروفة.
- action/event code ثابت قابل للفلترة.
- request ID إن كانت البنية الحالية توفره.
- trusted client IP باستخدام نفس سياسة البروكسي الآمنة الموجودة؛ لا تثق في
  `X-Forwarded-For` مباشرة.
- User-Agent محدود الطول ومُنظّف قبل التخزين.
- metadata قليلة ومسموح بها صراحة، لا dump عشوائي للطلب.

غطِّ على الأقل الأحداث ذات القيمة التشغيلية التالية:

- نجاح تسجيل الدخول.
- فشل تسجيل الدخول لحساب معروف، والوصول إلى lockout/رفض حساب مقفول.
- بدء/نجاح/فشل العمليات الحساسة لكلمة السر أو reset حيث يمكن تسجيلها بدون
  كشف وجود الحساب في response العام.
- تفعيل/تعطيل 2FA، استخدام recovery code، وتجديده.
- logout، إبطال جلسة، إبطال كل الجلسات، واكتشاف refresh replay.
- رفض self-lockout ورفض permission override المحميين من Gate 2A، إن لم يكونا
  مسجلين بالفعل في `AuditLog`.

قواعد غير قابلة للتفاوض:

- لا email خام، password، TOTP، recovery code، access/refresh/reset/step-up
  token، token hash، TOTP secret أو QR payload داخل `AuditLog`.
- حافظ على anti-enumeration: نفس status/message/timing للمسارات العامة بقدر
  السلوك الحالي، ولا تجعل السجل side channel للعميل.
- لمحاولة login على هوية غير معروفة: إن كان التسجيل الدائم مطلوبًا، استخدم
  fingerprint غير قابل للعكس ومفصول المجال (keyed HMAC) بدل البريد الخام؛
  وإلا اكتفِ بالـstructured security log. وثّق القرار.
- امنع write amplification: persistence للفشل يجب أن تكون bounded/coalesced
  أو rate-limited؛ لا صف قاعدة بيانات غير محدود لكل bot request.
- فشل كتابة audit لا يجوز أن يحوّل login فاشلًا إلى نجاح. حدّد بوضوح أين
  fail-closed مطلوب وأين التسجيل best-effort مع structured error log.

## الشريحة B — Refresh-token families and atomic reuse detection

طوّر `RefreshToken` الحالي بدل إنشاء نظام جلسات منفصل. صمّم migration أمامية
إضافية تحافظ على الصفوف الموجودة وتعطي كل legacy token عائلة مستقلة آمنة.

الخصائص المطلوبة، مع تكييف الأسماء للبنية الحالية:

- family identifier عشوائي غير مشتق من user id.
- public session reference آمن للواجهة، منفصل عن token/hash الداخلي.
- created/last-used/expiry/revoked/consumed metadata اللازمة فقط.
- successor relation أو ما يعادلها إذا احتاج منطق كشف replay ذلك.
- بقاء السر نفسه hash فقط كما هو الآن.

سلوك الدوران المطلوب:

1. token صالح وغير مستهلَك يتحول ذريًا إلى consumed، ويصدر successor داخل
   نفس family في transaction واحدة.
2. طلبان متزامنان لا يصدران successorين.
3. تقديم token مستهلَك مرة ثانية يُعتبر replay: تُلغى العائلة النشطة كلها،
   يُنشر access-token cutoff للمستخدم، ويُسجّل الحدث بدون السر.
4. token منتهي/ملغي/غير معروف يُرفض برسالة عامة آمنة؛ لا تخلط عدم الصلاحية
   العادي مع replay إلا إذا كان لديك tombstone موثوق يثبت الاستهلاك.
5. تغيير/reset كلمة السر، تعطيل الحساب/تغيير صلاحياته المؤثر، recovery الأمني،
   وعمليات logout/session revoke يجب أن تلغي النطاق الصحيح من العائلات.
6. لا تعمل global cleanup في hot path. احتفظ بالـtombstones مدة كافية لكشف
   replay ثم وفر cleanup محدودًا ومختبرًا إذا كان مطلوبًا.

وثّق بصدق trade-off الطلبين المتزامنين من نفس المتصفح: الأمان له الأولوية؛
إذا عومل الطلب الخاسر كـreplay وأُلغيَت العائلة، يجب أن تكون الواجهة قادرة على
العودة لتسجيل الدخول بوضوح بدل حل متساهل يفتح duplicate minting.

## الشريحة C — Self-service sessions and security activity

أضف API وواجهة داخل Profile/Security للمستخدم الحالي فقط:

- قائمة جلسات/عائلات refresh الفعالة بمعلومات آمنة: مرجع عام، بداية الجلسة،
  آخر نشاط، الانتهاء، وصف جهاز محدود، و`current` عندما يمكن إثباته.
- إلغاء جلسة واحدة يملكها المستخدم.
- إلغاء كل الجلسات الأخرى.
- قائمة مختصرة ومصفّحة لنشاط الأمان الخاص بالمستخدم من الأحداث المسموح بها.

لا تعرض token/hash/family id الداخلي، بريدًا أو بيانات مستخدم آخر، IP كاملًا
إن لم تكن له حاجة واضحة، أو payload التدقيق الخام. استخدم DTOs allowlist.

إلغاء جلسة أخرى عملية حساسة: أعد استخدام step-up الخاص بـGate 2B3A بغرض
جديد scope-bound مثل `session_revoke`/`other_sessions_revoke`، ولا تنشئ
نافذة password/TOTP موازية. اربط الإثبات بالجلسة المستهدفة أو بالعملية
الجماعية تحديدًا، واستهلكه مرة واحدة. إلغاء الجلسة الحالية عبر logout يظل
بتدفقه الطبيعي.

الواجهة يجب أن تكون:

- عربية وإنجليزية بالكامل، RTL/LTR من نظام اللغة الحالي.
- حالات loading/empty/error/success واضحة.
- تميّز "هذه الجلسة" وتطلب تأكيدًا واضحًا قبل الإلغاء.
- قابلة للكيبورد وقارئ الشاشة، مع focus management وlabels مرتبطة.
- لا تخزن step-up token أو أي سر في local/session storage.
- تستخدم مكونات design system الحالية ولا تكرر modal/buttons/toasts.

لا تضف في هذه الدفعة لوحة Super Admin لإدارة جلسات مستخدم آخر؛ هذه ميزة
أوسع تحتاج صلاحية وسياسة دعم مستقلة.

## التزامن وسلامة المعاملة

اختبارات PostgreSQL الحية إلزامية على الأقل لـ:

- refreshان متزامنان لنفس token: successor واحد فقط.
- replay مثبت يلغي العائلة ولا يترك successor صالحًا.
- race بين استخدام successor وإعادة استخدام parent: النتيجة fail-closed ولا
  يبقى للعائلة token فعال قابل للاستخدام.
- إلغاء جلسة متزامنًا مع refresh لا يعيد إحياء الجلسة.

SQLite unit/integration tests وحدها لا تثبت هذه الضمانات. أعد استخدام harness
المعزول الموجود، واحذف قاعدة الاختبار بعد التشغيل.

## Migration والتوافق

- migration أمامية واحدة، additive حيث يمكن، بلا تعديل migration قديمة.
- backfill حتمي وآمن لكل refresh row قائم؛ لا تجعل كل legacy rows عائلة واحدة.
- indexes/unique constraints مبنية على الاستعلامات الفعلية فقط.
- اختبر `upgrade -> downgrade -> upgrade` على PostgreSQL معزول، واذكر أثر
  rollback بصدق بعد بدء تدوير العائلات الجديدة.
- حافظ على عقد cookie/CSRF/CORS الحالي ولا تنقل refresh token إلى JavaScript.
- لا تغيّر response العام لطلب password reset بطريقة تكشف وجود البريد.

## اختبارات القبول الدنيا

إضافة إلى التزامن أعلاه:

- audit payloads لا تحتوي أي secret أو identifier محظور.
- unknown-user login/reset لا يغيّر response بما يكشف الحساب.
- الفشل المتكرر لا يضخم `AuditLog` بلا حد.
- login success/known failure/lockout/password/2FA/recovery/logout/replay
  تُسجّل وفق السياسة المعلنة.
- refresh family تُحفظ عبر rotation، وreuse يلغيها كلها.
- حساب inactive/deleted/bootstrap-incomplete لا يجدّد جلسة.
- المستخدم يرى جلساته فقط ولا يستطيع إلغاء session reference لمستخدم آخر.
- step-up purpose/target/session mismatch أو replay أو expiry يرفض الإلغاء.
- revoke one/revoke others يوقف refresh والجلسات المعنية فعلًا.
- API pagination/authorization/error contracts ثابتة ومختبرة.
- الواجهة العربية/الإنجليزية تمر type-check/build واختبارات المكونات المتاحة.

كل bug مؤكد أثناء التنفيذ يحصل على regression test قبل إغلاق الدفعة.

## ما هو خارج النطاق

- typed settings registry.
- إنشاء علاقة user→branch جديدة.
- step-up للـfinance/void/refund/period close.
- إدارة Super Admin لجلسات الآخرين.
- تغيير معمارية access token أو نقلها للتخزين الدائم في المتصفح.
- QR/Public Menu/Service Location.
- dependency جديدة إلا لو لا يوجد بديل آمن في الموجود، مع تبرير مكتوب أولًا.

## أوامر التحقق والتسليم

اكتشف الأوامر الفعلية واستخدم الموجودة أولًا. الحد الأدنى المتوقع:

```bash
bash scripts/agent-check.sh
cd backend
.venv/bin/pytest <auth/session targeted tests> -v
.venv/bin/pytest tests/ -v
.venv/bin/alembic heads
# PostgreSQL live concurrency suite with the repository's isolated harness
# isolated PostgreSQL upgrade -> downgrade -> upgrade cycle
cd ../frontend
pnpm --filter el-kheima type-check
pnpm --filter el-kheima build
cd ..
git diff --check
git status --short --branch
```

حدّث في النهاية فقط وبعد نجاح التحقق:

- `docs/audits/gate-2b3b-auth-audit-session-defense.md` كتقرير تنفيذي صادق.
- `PROJECT_STATUS.md`.
- `wagdy.md` بلغة بشرية.
- Project Cockpit snapshot/experience data دون ادعاء اعتماد Codex.
- قرار 0003 أو وثيقة القرار المناسبة إذا تغيّر عقد أمني دائم.

التقرير النهائي لكلودي يجب أن يفصل: ما وجده، التصميم، migration، transaction
boundaries، replay semantics، privacy/audit policy، API/UI، نتائج كل أمر،
المخاطر المتبقية، والملفات المتغيرة.

**توقف بعدها بلا commit وبلا push وبلا بدء Gate أخرى.**
