# الخطة النهائية الشاملة لتطبيق وموقع الخيمة

## Checkpoint تنفيذي ناسخ — 2026-07-29

- Mohamed أكد أن الخيمة تعمل بفرع تشغيلي واحد فقط حاليًا، وعيّن Codex قائد التنفيذ والمراجع النهائي.
- Gate 1 frontend/bootstrap/permissions/offline identity مكتملة محليًا ومختبرة، بلا selector ظاهر للفرع الواحد.
- full backend و93/93 frontend وtype-check/build وAlembic single-head كلها خضراء.
- وصول VPS الإداري مثبت بالمفتاح مع sudo؛ الأمن والحاويات والصحة والنسخ المحلي وتجديد TLS تم فحصها حيًا.
- النشر التالي **PAUSED** لحين حفظ ومصالحة شجرة الإنتاج غير النظيفة؛ لا pull/overwrite مباشر.
- Gate 9/domain **PAUSED**؛ IP-only هو القرار الساري، وتجديد شهادة IP اختُبر بنجاح.
- لا تزال master data وUAT الفعلي وoffsite backup والمراقبة شروط Go/No-Go.

| Gate | الحالة المثبتة في 2026-07-29 |
|---|---|
| 0 | COMPLETE |
| 1 | CODE COMPLETE — LOCAL FINAL REVIEW؛ النشر بعد مصالحة المصدر |
| 2 | PARTIAL — عقود QR/PWA الأساسية موجودة؛ device UAT باقٍ |
| 3 | DEPLOYED CONTAINMENT — chat/consent/truth fail-closed |
| 4 | PARTIAL — حقائق ومحتوى المالك غير مكتملة |
| 5 | BLOCKED ON APPROVED DATA — لا بيانات مختلقة |
| 6 | COMPLETE — SSH key/sudo/UFW/Fail2ban/ports verified |
| 7 | PARTIAL — onsite backup verified؛ offsite/monitoring/source reconciliation باقية |
| 8 | PARTIAL — IP TLS/health verified؛ device/business UAT باقٍ |
| 9 | PAUSED — IP-only؛ لا DNS switch بلا قرار مالك جديد |

> **قرار ناسخ بتاريخ 2026-07-26:** الإصدار الحالي IP-only على
> `191.218.161.133`، ولا يعتمد على `elkheimabeachresort.com` أو DNS. أي بنود
> نطاق/DNS أدناه اختيارية فقط إذا طلب المالك ذلك لاحقًا، وليست بوابة للنشر
> الحالي. حالة التنفيذ الفعلية موثقة في تسليم VPS-02.

**الحالة:** خطة تنفيذ حية؛ آخر تدقيق كود وVPS مثبت بتاريخ 2026-07-29
**النطاق:** `resort-os`، تطبيق الموظفين `frontend/apps/el-kheima`، موقع التسويق `elkheima-marketing-website`، الـBackend، قاعدة البيانات، والـVPS الجديد على Hostinger
**الهدف:** الوصول إلى إصدار إنتاج آمن، قابل للتشغيل والرجوع للخلف، ببيانات موثقة وليست تجريبية

> هذه الوثيقة خطة تنفيذ وليست تصريحًا بإجراء تغييرات إنتاجية فورية. لا يتم تغيير DNS أو VPS أو بيانات حقيقية قبل اجتياز بوابات القبول المحددة أدناه.

## 1. قواعد التنفيذ غير القابلة للتفاوض

1. لا يتم لمس ملفات الشات بوت التي يعمل عليها Claude حاليًا حتى ينتهي، ثم تتم مراجعة الفرق ودمجه من نقطة أساس واحدة.
2. كلمة مرور `root` التي ظهرت في لقطة الشاشة تعتبر مكشوفة. لا تُستخدم، وتُغيّر من لوحة Hostinger قبل أي نشر.
3. لا يتم تشغيل `backend/app/seed.py` في الإنتاج؛ الملف مخصص للتطوير ويحتوي حسابات وبيانات وأسعارًا تجريبية.
4. لا تُختلق بيانات معاملات أو بيانات شخصية: لا حجوزات، موظفين، عملاء، عقود، أرصدة، أرقام غرف أو أسعار نهائية من دون ملف مصدر واعتماد المالك.
5. أي معلومة عامة قابلة للتغير، مثل التقييمات والأسعار والمواعيد، تُحفظ بمصدر وتاريخ تحقق ولا تُكتب كحقيقة دائمة داخل الواجهة.
6. كل صلاحية تُفرض في الـBackend أولًا. إخفاء زر في الـFrontend ليس حماية.
7. النشر يكون بصور Docker ثابتة مرتبطة بـGit SHA، وليس بناءً عشوائيًا مباشرًا فوق الإنتاج.
8. لا يُنفذ ترحيل قاعدة بيانات هدّام في نفس إصدار حذف الكود القديم؛ نستخدم أسلوب expand/migrate/contract.
9. لا يتم تعطيل دخول root بكلمة المرور قبل اختبار جلسة SSH ثانية ناجحة بالمفتاح وحساب sudo غير root.
10. كل بوابة تنتهي باختبارات قبول وخطة تراجع موثقة.

## 2. ترتيب الأولويات

- **[High]** خطر أمني، تسريب بيانات، كسر للنشر، فساد معاملات، أو مانع مباشر للإطلاق. يجب إغلاقه قبل الإنتاج.
- **[Medium]** خلل جودة أو تشغيل أو أداء قد يتحول إلى حادث إنتاجي. يُغلق قبل الإطلاق العام ما لم يُعتمد استثناء مؤقت بمالك وموعد انتهاء.
- **[Low]** تحسين قابل للتأجيل لا يؤثر في الأمان أو صحة البيانات. يُجمع بعد استقرار الإصدار.

## 3. ملخص المخاطر عند إنشاء الخطة (سجل تاريخي؛ checkpoint أعلاه هو الحالة الحالية)

### [High] موانع الإنتاج

| الرمز | الملاحظة | الأثر |
|---|---|---|
| H-01 | مسارات `/ops` وعدد من PMS APIs متاحة عمليًا لأي مستخدم نشط | كشف بيانات ضيوف وغرف وإمكانية تعديل التشغيل |
| H-02 | عقد الفرع غير متطابق؛ الواجهة تفترض `branch_id` والـBackend لا يعيده في المستخدم | تنفيذ إجراءات على فرع خاطئ أو الاعتماد على fallback للفرع 1 |
| H-03 | Service Worker لتطبيق الموظفين يخزن/يكاش طلبات API حساسة بشكل واسع | بيانات قديمة أو بيانات مشغل سابق تظهر دون قصد |
| H-04 | توليد QR يستخدم عناوين تطوير/fallback غير صحيحة | QR إنتاجي يفتح نطاقًا أو منفذًا خاطئًا |
| H-05 | `docker-compose.prod.yml` ما زال يبني تطبيقًا عامًا محذوفًا ويستخدم مسارًا مطلقًا لموقع التسويق | فشل بناء الإنتاج وعدم قابلية النقل |
| H-06 | موقع التسويق يحتفظ بمنطق توكنات الموظفين داخل العميل والـService Worker | توسيع غير ضروري لسطح سرقة الرموز |
| H-07 | الشات/contact عامان ويحتاجان حدود إدخال ومعدل واستهلاك وحماية من إساءة الاستخدام | تكلفة غير محدودة، spam، PII، ومخرجات غير موثوقة |
| H-08 | معلومات وهوية وأسعار وتقييمات متعارضة أو غير موثقة في الموقع وStructured Data | تضليل الزائر ومخاطر SEO وثقة |
| H-09 | الـVPS بلا Firewall Rules ظاهرة، وSSH بالمفتاح غير مهيأ، وكلمة root ظهرت في صورة | خطر سيطرة على الخادم قبل بدء التشغيل |
| H-10 | النشر والنسخ/الاستعادة الحالية بها افتراضات أسماء وIP قديمة ولا تغطي أول نشر | لا يوجد تراجع موثوق عند الفشل |
| H-11 | Redis واحد بسياسة `allkeys-lru` للكاش وCelery broker | إمكانية طرد مهام Celery أو مفاتيح تشغيلية مهمة |
| H-12 | أسرار الإنتاج لها قيم fallback ضعيفة، والاتصالات/الموارد غير مضبوطة على VPS بقدرة 2 vCPU | اختراق أو نفاد اتصالات/موارد |

### [Medium] جودة وتشغيل

| الرمز | الملاحظة | المطلوب |
|---|---|---|
| M-01 | اختبار i18n يفشل بسبب مفتاح ناقص | جعل i18n gate إلزاميًا في CI |
| M-02 | اختبار contrast واحد يفشل | إصلاح الألوان وإعادة اختبار a11y |
| M-03 | خريطة أدوار الواجهة غير مكتملة وقد تفشل بشكل مفتوح للدور غير المعروف | أنواع مشتركة وfail-closed |
| M-04 | WebSocket متابعة الوردية لا يعيد الاتصال عند فتح وردية جديدة | lifecycle/reconnect واختبارات |
| M-05 | ثغرات dependencies في التطبيق والموقع، منها PostCSS وسلسلة `@vueuse/head` القديمة | ترقيات محدودة واختبارات regression |
| M-06 | التحليلات ووسوم الأطراف الثالثة تبدأ قبل موافقة الزائر | consent افتراضي مرفوض وتحميل بعد opt-in |
| M-07 | لا توجد Security Headers/CSP إنتاجية كافية للموقع | Report-Only ثم enforce |
| M-08 | CI لا يشغّل كل اختبارات PostgreSQL/concurrency ولا يبني الصور فعليًا | Pipeline إنتاجي كامل |
| M-09 | لا توجد قناة إدخال بيانات إنتاجية ذات dry-run وvalidation وaudit | staging/import pipeline |
| M-10 | لا توجد مراقبة موحدة وتنبيهات وrunbooks كافية | metrics/logs/error tracking/alerts |

### [Low] تحسينات مؤجلة

- تقسيم bundle تطبيق الموظفين وتحميل الصفحات واللغات عند الطلب.
- تقليل `any` والمسارات النصية للـAPI وتقسيم المكونات التي تجاوزت ألف سطر.
- توحيد polish البصري وحالات empty/loading/error والطباعة.
- تحسين صور التسويق، WebP/AVIF، preload محدود، وتنظيف CSS غير المستخدم.
- إضافة لوحة داخلية لصحة التكاملات بدل الرجوع للسجلات.

## 4. الخطة التنفيذية ذات البوابات

التقدير الواقعي لمنفذ واحد مع مراجعة وUAT هو **4–6 أسابيع**، ويتغير بحسب سرعة تسليم البيانات واعتمادها. ترتيب البوابات إلزامي؛ يمكن تنفيذ بعض أعمال الجودة بالتوازي فقط بعد انتهاء تعديل الشات بوت.

### Gate 0 — تجميد نقطة الأساس والتنسيق

**الأولوية:** [High]
**المدة التقديرية:** نصف يوم إلى يوم

#### التنفيذ

1. انتظار Claude حتى ينهي عمل الشات بوت.
2. حفظ تقرير الملفات التي غيّرها في المستودعين ومراجعة diff أمنيًا ووظيفيًا.
3. منع أي merge يحتوي أسرارًا أو prompts حساسة أو migrations متعددة الرؤوس.
4. إنشاء branch تنفيذ واحد من أحدث `main` بعد دمج عمل Claude.
5. إعادة تشغيل baseline:
   - Backend unit/integration.
   - Alembic single-head.
   - Frontend typecheck/build/unit/i18n.
   - Marketing typecheck/build/audit.
6. تسجيل النتائج في تقرير Gate 0؛ لا نعتمد الاختبارات التي كانت ناجحة قبل التغييرات الجديدة.

#### القبول

- شجرة العمل معروفة ولا توجد تعديلات متضاربة مجهولة.
- migration head واحد.
- كل فشل baseline مسجل بمالك وأولوية.
- لا يوجد secret في Git history الجديد.

#### التراجع

- لا يوجد تغيير إنتاجي؛ نعود إلى Git SHA السابق لفرع التنفيذ فقط، دون حذف تعديلات Claude أو تعديلات المستخدم.

---

### Gate 1 — احتواء المخاطر الأمنية والصلاحيات والفروع

**الأولوية:** [High]
**المدة التقديرية:** 3–5 أيام

#### Backend

1. إضافة صلاحيات دقيقة، على الأقل:
   - `pms.rooms.view`, `pms.rooms.manage`
   - `pms.bookings.view`, `pms.bookings.create`
   - `pms.bookings.check_in`, `pms.bookings.check_out`, `pms.bookings.cancel`
   - `pms.housekeeping.view`, `pms.housekeeping.update`
2. تطبيق `require_permission` على كل endpoint، لا على router العام فقط.
3. بعد جلب أي كيان بالـID، التحقق أن فرعه ضمن الفروع المسموح بها للمستخدم.
4. تعريف واضح لـsuper-admin global access، مع audit لأي وصول عابر للفروع.
5. توحيد عقد جلسة المستخدم ليعيد:
   - `default_branch_id`
   - `allowed_branch_ids`
   - `effective_permissions`
   - بيانات الدور والحساب الأساسية
6. رفض الفرع القادم من العميل إذا لم يكن ضمن عضوية المستخدم.
7. اعتبار الدور أو الصلاحية غير المعروفة مرفوضة افتراضيًا.

#### Database

إضافة جدول عضويات الفروع:

```text
user_branch_memberships
  id
  user_id -> users.id
  branch_id -> branches.id
  is_default
  is_active
  created_at / created_by
  revoked_at / revoked_by
```

- unique على `(user_id, branch_id)`.
- default واحد نشط لكل مستخدم.
- backfill من `HR.Employee.user_id -> Employee.branch_id`.
- تقرير بالمستخدمين الذين ليس لهم Employee أو فرع قبل فرض القيود.
- لا يتم حذف الاعتماد القديم إلا في إصدار contract لاحق.

#### Frontend

1. حذف `branchId ?? 1` وكل fallback صامت للفرع.
2. bootstrap واحد للجلسة والصلاحيات قبل إنشاء القائمة أو فتح المسار.
3. إضافة `requiredPermission` typed داخل route meta.
4. `/ops` والقوائم والأزرار تعتمد على الصلاحيات الفعلية.
5. التحقق في الواجهة يحسن UX فقط؛ الـBackend يظل صاحب القرار.
6. توحيد قائمة الأدوار مع الـBackend، بما فيها `timeshare_agent`.

#### اختبارات القبول

- مستخدم نشط بلا صلاحية يحصل على `403` لكل read/write حساس.
- housekeeper يرى ويحدث housekeeping فقط وفق السياسة المعتمدة.
- موظف فرع A لا يقرأ كيان فرع B حتى لو عرف ID.
- تبديل الفرع يتم server-validated ويسجل في audit.
- super-admin يعمل بلا كسر invariants الحالية.
- اختبارات matrix للأدوار × الفروع × العمليات تعمل على PostgreSQL.

#### التراجع

- الجداول والإضافات additive.
- عند فشل الواجهة يمكن إرجاع صورة التطبيق السابقة مع إبقاء الجداول الجديدة.
- لا يُحذف أي عمود أو مسار قديم في هذا الإصدار.

---

### Gate 2 — عقد QR وPWA والـPublic API

**الأولوية:** [High]
**المدة التقديرية:** 2–3 أيام

#### QR والنطاقات

1. اعتماد متغير واحد موثوق للعنوان العام:
   - Backend: `PUBLIC_SITE_URL`
   - Frontend build: `VITE_PUBLIC_SITE_URL`
2. إضافته صراحة إلى Docker build args وإلى فحص preflight.
3. منع أي fallback إلى `localhost` أو منافذ التطوير في production.
4. اختبار QR حقيقي من هاتف خارج شبكة الخادم لكل نوع:
   - غرفة، طاولة، موقع شاطئ، survey، guest session.
5. توقيع/تخمين أقل للمعرفات الحساسة، وTTL أو revoke حين يلزم.

#### Staff PWA

1. عدم Cache أي استجابة:
   - تحتوي PII.
   - مرتبطة بمستخدم/فرع/وردية.
   - حجوزات، غرف، housekeeping، مخزون، حسابات، جلسات.
2. حصر الـRuntime Cache في أصول static وقراءات عامة آمنة فقط.
3. مسح API caches عند logout/الترقية، وربط سجلات IndexedDB التشغيلية
   بالمستخدم المنشئ؛ لا تُحذف مبيعات offline غير المتزامنة ولا تظهر أو
   تُرسل تحت هوية المستخدم التالي عند logout/PIN switch.
4. إظهار update prompt وتطبيق versioned cache migration.
5. فصل manifest direction/language إن كان دعم اللغتين مطلوبًا فعليًا.

#### Public API contract

إنشاء عقد صريح تحت `/api/v1/public`:

- `GET /bootstrap?site=<slug>`: هوية الفرع العامة، اللغات، وسائل الاتصال المعتمدة، الـfeature flags، ومنافذ الخدمة.
- قوائم عامة منفصلة للمنيو/الخدمات بقواعد cache وETag.
- contact/chat/guest endpoints ترجع `Cache-Control: no-store`.
- تحديد الفرع من host/slug موثق، لا من `branch_id=1` يرسله الزائر.

#### القبول

- كل QR يحمل origin إنتاجي صحيحًا.
- لا تظهر بيانات مستخدم سابق بعد logout أو تبديل الحساب.
- الـPublic API لا يعيد حقولًا داخلية أو أسرارًا.
- اختبارات cache headers وoffline/logout تعمل آليًا.

---

### Gate 3 — أمن وتوافق موقع التسويق والشات بوت

**الأولوية:** [High] للأمن والبيانات، [Medium] للجودة
**المدة التقديرية:** 3–5 أيام بعد انتهاء Claude

#### فصل العام عن الموظفين

1. حذف staff access/refresh token logic من موقع التسويق.
2. حذف تخزين bearer tokens وطلبات gate القديمة من `public/sw.js`.
3. الـoffline العام يحتفظ بمسودة الطلب فقط، ثم يعيد التحقق من guest session عند الاتصال ويرسل بـidempotency key.
4. استبدال عميل API بعميل Public صغير لا يعرف مسارات دخول الموظفين.
5. حذف/استبدال الطلبات الميتة مثل `/modules/public` و`/settings/public` بعقد `/public/bootstrap`.
6. احترام `route.meta.hidePublicLayout` في QR/survey operational pages.

#### الشات بوت بعد استلام عمل Claude

1. مراجعة endpoint الموحد، auth model، timeouts، وإدارة الأخطاء.
2. rate limits مستقلة حسب IP وguest/session مع سقف يومي للتكلفة.
3. حد أقصى لحجم الرسالة، عدد الأدوار، السياق، وزمن الاستجابة.
4. عدم إرسال أسرار، تعليمات نظامية، أو بيانات موظفين/ضيوف للنموذج.
5. تصنيف محتوى المستخدم على أنه غير موثوق ومقاومة prompt injection.
6. مخرجات النموذج غير موثوقة:
   - لا `v-html` بدون sanitizer موثوق.
   - الأفضل Markdown AST بعناصر مسموحة فقط.
   - روابط `http/https/tel` وWhatsApp المعتمد فقط.
   - `noopener,noreferrer` للروابط الخارجية.
7. PII minimization، retention معلن، وإخفاء البيانات من logs.
8. circuit breaker ورسالة fallback مفيدة عند انقطاع مزود الذكاء الاصطناعي.
9. مجموعة red-team: XSS، javascript URLs، prompt leakage، إساءة التكلفة، payload كبير، تكرار retry.

#### Contact form

1. Pydantic schema typed مع max lengths وnormalization.
2. الفرع يحدد من إعداد الموقع server-side.
3. per-IP + per-contact rate limit، honeypot، وتصعيد CAPTCHA عند السلوك المشبوه فقط.
4. idempotency، حالة spam، audit، ورسالة نجاح لا تكشف تفاصيل CRM.
5. timeout/retry محدود للتكامل الخارجي، مع queue عند الحاجة.

#### Headers وConsent

1. Security headers من Nginx:
   - `Content-Security-Policy` بنمط Report-Only أولًا ثم enforce.
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy`
   - `Permissions-Policy`
   - `frame-ancestors` عبر CSP
   - HSTS بعد نجاح HTTPS لكل النطاقات المطلوبة.
2. للـService Worker ملف CSP مناسب خاص به.
3. GA/GTM/Meta Pixel/TripAdvisor لا تُحمّل قبل opt-in.
4. consent الافتراضي denied، والرفض يبقيها غير محملة.
5. سياسة خصوصية عربية/إنجليزية تشرح الغرض، الأطراف، المدة، والحذف.

#### Dependencies

- إزالة `@vueuse/head`/نسخ `unhead` المكررة واستخدام حزمة واحدة مدعومة.
- ترقية `vue-tsc` وVite/ملحقاته إلى إصدارات مصححة متوافقة، دون قفزة majors غير مختبرة.
- تحديث PostCSS في تطبيق الموظفين إلى إصدار مصحح.
- قبول النشر يتطلب عدم وجود High/Critical production vulnerability؛ أي استثناء يحتاج سببًا ومالكًا وتاريخ انتهاء.

#### القبول

- لا staff tokens في LocalStorage/IndexedDB/Service Worker للموقع العام.
- لا XSS من رسالة chatbot أو action URL.
- analytics network requests = صفر قبل الموافقة.
- CSP report نظيف للمسارات الأساسية ثم enforce.
- contact/chat abuse tests وrate-limit tests ناجحة.
- typecheck/build/unit/e2e/a11y ناجحة.

---

### Gate 4 — حقيقة المحتوى والهوية وSEO

**الأولوية:** [High] للادعاءات المضللة، [Medium] لتحسين SEO
**المدة التقديرية:** 2–3 أيام، ويتوقف على اعتماد المالك

#### سجل حقائق موحد

إنشاء `content_facts` أو ملف content versioned قابل للنشر يحتوي:

```text
key
locale
value
source_url
source_type
last_verified_at
approved_by
approved_at
expires_at
status: draft | approved | expired
```

#### البيانات الأولية المقترحة

| الحقيقة | القيمة الأولية | الحالة |
|---|---|---|
| الاسم التجاري | El Kheima Beach / الاسم العربي المعتمد | يحتاج اعتماد spelling النهائي |
| الموقع | Sharm El Maya, Sharm El Sheikh, South Sinai | موثق بالموقع الرسمي القديم ويحتاج اعتماد المالك |
| الهاتف | `+20 12 213 0000`، `+20 100 444 4300`، `+20 122 213 0000` | يتحقق المالك من الأرقام النشطة قبل النشر |
| البريد | `info@elkheimabeachresort.com` | يتحقق المالك من الملكية والاستقبال |
| العملة/المنطقة | EGP / Africa/Cairo | قيمة تشغيلية معتمدة مبدئيًا |
| التقييمات | لا قيمة ثابتة | تعرض من مصدر وتاريخ، أو تحذف |
| الأسعار | لا تعتمد من صفحات الموقع الحالية | تستورد من قائمة أسعار مالكها محدد ومدة صلاحيتها معلومة |

#### التنظيف الإلزامي

1. إزالة ادعاءات 5-star/3-star/120 rooms/#1/review counts وأرقام الزوار غير المثبتة.
2. إزالة `aggregateRating` وreviews المصطنعة من schema.org.
3. عدم تحويل نص مولد بالذكاء الاصطناعي إلى حقيقة دون مراجعة ومصدر.
4. توحيد الاسم والنطاق والبريد والعنوان في:
   - navbar/footer/contact
   - OpenGraph
   - JSON-LD
   - sitemap/robots
   - الشات بوت
   - قوالب البريد.
5. حذف `/spa` وأي sitemap route غير موجود، وإضافة canonical/hreflang صحيح.
6. حفظ الأسعار بعملة وضرائب وتاريخ بداية/نهاية وموافقة.

#### القبول

- لا ادعاء عام بلا مصدر/اعتماد.
- schema validator وSEO crawl بلا صفحات ميتة أو canonical متعارض.
- تطابق العربية والإنجليزية في الحقائق لا في الترجمة الحرفية فقط.

---

### Gate 5 — قاعدة بيانات إنتاجية وبيانات حقيقية

**الأولوية:** [High] لصحة البيانات، [Medium] لأتمتة الاستيراد
**المدة التقديرية:** 3–5 أيام برمجية، ومدة منفصلة لجمع/اعتماد البيانات

#### ممنوع في الإنتاج

- تشغيل seed التطوير.
- حسابات `Demo@...`.
- حجوزات وعملاء وعقود وأرصدة opening وهمية.
- أرقام غرف/طاولات/وحدات أو أسعار مخترعة.
- ضرائب أو تأمينات اجتماعية قديمة من seed 2024.

#### Production bootstrap

إنشاء أوامر idempotent منفصلة:

1. `bootstrap admin`: مستخدم مدير مسمى، كلمة مؤقتة عشوائية، تغيير إجباري، وتفعيل 2FA.
2. `bootstrap reference`: العملات، المنطقة الزمنية، الوحدات، الحالات، وسياسات النظام المعتمدة.
3. `import validate --dry-run`: قراءة CSV/XLSX إلى staging tables.
4. تقرير أخطاء بالصف والسطر والحقل، دون partial commit.
5. `import apply --checksum ...`: تطبيق transactionally مع idempotency key وaudit.
6. `import reconcile`: مقارنة المصدر بعدد السجلات والأرصدة والـtotals.

#### مجموعات البيانات المطلوبة من المالك

| المجموعة | الحد الأدنى |
|---|---|
| المنشأة والفروع | الاسم القانوني/التجاري، العنوان، الضرائب، وسائل الاتصال، أوقات العمل |
| PMS | أنواع الغرف، أرقام الغرف، السعة، الحالة، rate plans، الضرائب والسياسات |
| المطاعم والكافيه | المنافذ، التصنيفات، الأصناف، modifiers، الوصفات، الطاولات، الأسعار |
| الشاطئ والبوابة | المواقع/الكراسي، أنواع التذاكر، الأسعار، الصلاحية |
| المخزون | المنتجات، الوحدات والتحويلات، المخازن، الموردون، opening stock بتاريخ قطع |
| HR | الموظفون، الكود، الفرع، القسم، الوظيفة، الوردية، حالة التعيين، الصلاحيات |
| TimeShare/Leasing/B2B | الوحدات والعملاء والعقود والأرصدة بعد مراجعة قانونية/مالية |
| المالية | chart of accounts، الضرائب، طرق الدفع، opening balances واعتماد المحاسب |

#### الإعدادات القانونية المتغيرة

- VAT للمطاعم/الكافيهات السياحية: القيمة المرجعية الحالية 14% وفق مصلحة الضرائب المصرية، لكن تطبيقها على كل منتج/خدمة يعتمد بتصنيف محاسب.
- حدود أجر الاشتراك التأميني من 2026-01-01: حد أدنى 2,700 جنيه وحد أقصى 16,700 جنيه وفق الهيئة القومية للتأمين الاجتماعي.
- شرائح ضريبة المرتبات والإعفاءات تحفظ بإصدارات `effective_from/effective_to/source_url/approved_by` ولا تُستنتج من seed.
- service charge أو نسب فندقية أخرى لا تفترض تلقائيًا؛ يلزم قرار المالك والمحاسب.

#### القبول

- dry-run بلا أخطاء حرجة.
- totals والمخزون الافتتاحي والعقود موقعة من صاحب البيانات.
- إعادة تشغيل نفس import لا تنشئ duplicates.
- كل تغيير له source/checksum/user/timestamp.
- نسخة احتياطية قبل الاستيراد واختبار استعادة بعده في بيئة منفصلة.

---

### Gate 6 — تجهيز Hostinger VPS بأقل صلاحية

**الأولوية:** [High]
**المدة التقديرية:** 1–2 يوم

#### الحالة التي تم التحقق منها

- VPS: Ubuntu 24.04 LTS، 2 vCPU، 8 GB RAM، 100 GB disk.
- عنوان الخادم: `191.218.161.133`.
- SSH يرد، لكن المفتاح المحلي الحالي غير مصرح به.
- Hostinger firewall rules الظاهرة = صفر.
- Hostinger MCP غير مضاف حاليًا إلى إعداد Codex.
- Node المحلي 20؛ الإصدار الحالي من Hostinger MCP يذكر Node 24+.

#### وصول SSH الآمن

1. تغيير كلمة مرور root المكشوفة من hPanel.
2. إضافة المفتاح العام الحالي عبر Hostinger، دون نقل private key.
3. الدخول مرة واحدة فقط لعمل inventory read-only.
4. إنشاء مستخدم `deploy`:
   - مفتاح SSH مستقل.
   - sudo مضبوط.
   - لا password login.
5. ضبط Hostinger Firewall ثم UFW بالترتيب الآمن:
   - 22 من IP إداري ثابت أو VPN/Tailscale؛ إن لم يتوفر، مؤقتًا مع fail2ban ثم التضييق.
   - 80/443 للعامة.
   - منع 5432/5436 و6379/6381 و8000/8005 من الإنترنت.
6. اختبار جلسة `deploy` ثانية.
7. تعطيل `PasswordAuthentication` و`PermitRootLogin` بعد نجاح الاختبار فقط.
8. unattended security updates، fail2ban، time sync، وaudit لملفات authorized_keys.

#### Hostinger MCP/API

1. استخدام OAuth PKCE الموصى به، لا token دائم داخل repo أو TOML.
2. إضافة خادمين محدودين بدل صلاحية شاملة:
   - Hostinger VPS MCP.
   - Hostinger DNS MCP.
3. تشغيلهما في Node 24 معزول، دون تغيير runtime الخاص بالمشروع.
4. ضبط Codex approval mode على `writes`:
   - القراءة آلية.
   - أي إنشاء/تعديل/حذف يحتاج موافقة.
5. في شاشة Hostinger يتم تفعيل VPS وDomains/DNS فقط مبدئيًا، وتعطيل Billing/Email/E-commerce وأي منتج خارج النطاق.
6. لو اضطررنا إلى API token:
   - token قصير العمر.
   - أقل صلاحيات ممكنة.
   - في environment secret فقط.
   - revoke بعد bootstrap.
7. Docker Manager التجريبي لا يكون مسار النشر الوحيد؛ نستخدمه للمراقبة أو الأعمال المحدودة فقط.

#### قبول Gate 6

- دخول SSH بمستخدم `deploy` ومفتاح، وroot/password موقوفان بأمان.
- فحص خارجي يظهر 80/443 وSSH المقيد فقط.
- MCP يستطيع قراءة inventory، وأول write يطلب موافقة.
- لا secret في shell history أو Git أو screenshots جديدة.

---

### Gate 7 — بنية النشر والنسخ والمراقبة

**الأولوية:** [High]
**المدة التقديرية:** 2–4 أيام

#### Compose والخدمات

1. إزالة خدمة `public_site` المحذوفة.
2. جعل مسار موقع التسويق داخل build context قابل للنقل، أو نقله إلى monorepo/صورة GHCR مستقلة.
3. فصل Redis:
   - `redis-cache`: سياسة eviction مناسبة للكاش.
   - `redis-broker`: `noeviction` وpersistence وفق اختبار Celery.
4. PostgreSQL وRedis على شبكة داخلية فقط، بلا public ports.
5. إزالة كل production password fallback وإيقاف التشغيل إن غاب secret.
6. ضبط مبدئي مناسب لـ2 vCPU:
   - Web workers: 2 ثم تعديل بالقياس.
   - Celery concurrency: 1–2.
   - SQLAlchemy pool صغير وقابل للضبط.
7. resource limits وhealth checks وlog rotation.
8. `no-new-privileges` وcapabilities أقل وread-only filesystem حيث يتوافق.
9. pin للإصدارات والصور، وSBOM/Trivy قبل النشر.

#### صور ثابتة وCI/CD

1. GitHub Actions يبني backend/staff/marketing.
2. tag لكل صورة = commit SHA، ثم push إلى GHCR.
3. Gates إلزامية:
   - Backend PostgreSQL كامل، بما في ذلك concurrency.
   - Alembic single-head وupgrade test.
   - Frontend typecheck/unit/i18n/a11y/build.
   - Marketing typecheck/unit/e2e/security/a11y/build.
   - dependency audit، secret scan، image scan.
   - compose config وactual image build.
4. deploy بعد approval يدوي إلى `/opt/resort-os/releases/<sha>`.
5. preflight، backup، pull، migration expand، health/smoke، ثم تحويل Nginx.
6. الاحتفاظ بآخر صورتين/ثلاث صور ناجحة للرجوع السريع.

#### النسخ والاستعادة

1. إصلاح container/project names في scripts، واستخدام `.env.prod` الصحيح.
2. first-deploy path لا يحاول backup قاعدة غير موجودة.
3. نسخة PostgreSQL يومية مشفرة خارج الـVPS، مع checksum وسياسة retention.
4. Hostinger weekly backup طبقة إضافية، لا النسخة الوحيدة.
5. اختبار restore شهريًا إلى قاعدة scratch.
6. أهداف أولية:
   - RPO: 24 ساعة، أو أقل إن اعتمد WAL archiving.
   - RTO: ساعتان للخدمة الأساسية بعد اكتمال runbook.
7. استعادة Hostinger الكاملة تستخدم فقط كخيار كارثي لأنها تستبدل محتوى الخادم.

#### المراقبة

- uptime checks للـedge و`/health/ready`.
- CPU/RAM/disk/inodes/container restarts/Postgres connections/Redis memory/Celery queue depth.
- error tracking للواجهة والخلفية مع scrub للـPII.
- structured logs مع request ID وuser/branch ID غير حساس.
- تنبيه عند فشل backup أو امتلاء disk أو ارتفاع 5xx أو queue.
- runbooks: deploy failure، migration failure، DB restore، secret rotation، AI provider outage.

#### القبول

- نشر إصدار staging ثم الرجوع إلى SHA سابق دون فقد بيانات.
- استعادة backup فعلية ناجحة في scratch.
- لا منفذ قاعدة/Redis ظاهر خارجيًا.
- kill/restart container يمر health checks وتعود الخدمة.

---

### Gate 8 — DNS وTLS وStaging وUAT

**الأولوية:** [High]
**المدة التقديرية:** 2–4 أيام، ويتوقف على قرار النطاق

#### تصميم النطاق المقترح

بعد تأكيد النطاق المملوك:

- apex و`www`: موقع التسويق.
- `app`: تطبيق الموظفين.
- `/api` يمر same-origin من كل واجهة إلى الـBackend؛ لا نكشف `api` للعامة إلا لحاجة موثقة.
- staging subdomains محمية بكلمة/allowlist ولا تدخل محركات البحث.

> لم تظهر حاليًا سجلات DNS فعالة لـ`alkhaymaresort.com`، بينما الموقع القديم يستخدم `elkheimabeachresort.com`. لا يتم شراء أو تحويل أو تعديل DNS قبل تأكيد الملكية والنطاق النهائي.

#### التنفيذ

1. TTL = 300 قبل القطع بـ24 ساعة إن أمكن.
2. A records إلى `191.218.161.133`، وAAAA فقط إذا تم إعداد IPv6 واختباره.
3. CAA مناسب لمصدر الشهادة.
4. Nginx config حقيقي بلا `yourdomain.com` أو IP قديم.
5. إصدار TLS وتجديد آلي واختبار renew.
6. CORS origins exact، وCookies `Secure`, `HttpOnly`, `SameSite` حسب التدفق.
7. HSTS بعد نجاح apex/www/app وعدم وجود mixed content.

#### UAT

- Arabic/English، هاتف/تابلت/desktop.
- login/logout/2FA/refresh/expiry.
- كل role والفرع والوردية.
- QR من كاميرا هاتف حقيقية.
- booking/check-in/check-out/housekeeping.
- dining/gate/inventory حسب نطاق الإصدار.
- marketing contact/chat/consent/offline/update.
- فشل الشبكة، duplicate submit، timeouts، وعودة الخدمة.
- تقرير signed من operations/finance/owner للوظائف والبيانات.

#### Go/No-Go

لا Go إذا وُجد:

- High مفتوح.
- High/Critical dependency vulnerability بلا تخفيف معتمد.
- فشل backup/restore.
- اختبار صلاحية عابر للفروع يفشل.
- QR أو DNS/TLS أو health check غير مستقر.
- بيانات مالية/أسعار/اتصال غير معتمدة.

---

### Gate 9 — الإطلاق والمتابعة

**الأولوية:** [High] للإطلاق، [Medium] للمتابعة
**المدة:** يوم إطلاق + 72 ساعة مراقبة مكثفة

#### Runbook القطع

1. تجميد تغييرات البيانات المرجعية.
2. أخذ backup والتحقق من checksum.
3. تسجيل SHA والصور والمigrations ومالك القرار.
4. نشر release، تشغيل expand migration، smoke tests.
5. تعديل DNS فقط بعد صحة الخدمة على origin.
6. مراقبة 5xx/latency/DB/Redis/queues/JS errors/chat cost.
7. تراجع إلى الصورة السابقة عند فشل التطبيق.
8. بالنسبة لقاعدة البيانات: roll-forward آمن افتراضيًا؛ restore فقط بقرار incident commander لأنه قد يفقد معاملات أحدث.

#### أول 72 ساعة

- مراجعة كل 2–4 ساعات في اليوم الأول.
- مراجعة يومية للنسخ، السعة، أخطاء الدخول، checkout، QR، chat/contact.
- تسجيل incidents والـnear misses.
- عدم تنفيذ [Low] أثناء نافذة الاستقرار إلا إذا عالج incident.

## 5. حزمة [Medium] بعد إغلاق الـHigh

1. إصلاح i18n والcontrast وإضافتهما كـrequired CI gates.
2. إعادة اتصال WebSocket وربطه بدورة حياة الوردية.
3. إضافة Playwright journeys للمسارات الحرجة.
4. Contract tests بين موقع التسويق والـPublic API.
5. لوحة لصحة الـAI/WhatsApp/payment/email والتكلفة والـrate-limit.
6. performance budgets:
   - JS initial budget لكل واجهة.
   - صور responsive وlazy loading.
   - قياس LCP/INP/CLS من production telemetry.
7. توثيق data ownership ومدة الاحتفاظ والحذف.
8. quarterly access review وdependency update cadence.

## 6. حزمة [Low] محدودة

تُنفذ في sprint واحد بعد الاستقرار، ولا تؤخر الإطلاق:

- تقسيم المكونات العملاقة وتنظيف `any`.
- توحيد API route constants/generated client.
- تحسين skeletons وempty states والطباعة.
- تحسين الصور وprefetch المدروس.
- إزالة ملفات وتعليقات ومكونات قديمة مثبت عدم استخدامها.
- تحسين developer experience والتوثيق المحلي.

## 7. Definition of Done النهائي

يعتبر المشروع جاهزًا فقط عندما تتحقق جميع النقاط:

- [ ] لا [High] مفتوح.
- [ ] صلاحيات backend واختبارات branch isolation ناجحة.
- [ ] لا tokens موظفين أو PII في public caches.
- [ ] الشات بوت/contact مقاومان للإساءة والمخرجات معقمة.
- [ ] المحتوى والأسعار والهوية معتمدة ومصدرها مسجل.
- [ ] production seed غير مستخدم، والاستيراد idempotent ومراجع.
- [ ] CI كامل أخضر، وimages ثابتة ممسوحة أمنيًا.
- [ ] SSH key-only وحساب deploy وfirewall وMCP least-privilege.
- [ ] DNS/TLS/CORS/cookies/security headers صحيحة.
- [ ] backup وrestore وrollback تم اختبارها عمليًا.
- [ ] UAT موقع من التشغيل والمالية والمالك.
- [ ] مراقبة وتنبيهات وrunbooks تعمل.
- [ ] 72 ساعة استقرار بلا incident حرج.

## 8. ما يحتاجه التنفيذ من المالك

هذه البنود لا تمنع إصلاح الكود، لكنها تمنع cutover إنتاجي:

1. تأكيد النطاق النهائي وملكيته: `alkhaymaresort.com` أم `elkheimabeachresort.com` أم غيرهما.
2. تنفيذ OAuth لـHostinger MCP أو إضافة المفتاح العام من hPanel.
3. اعتماد الاسم التجاري العربي والإنجليزي وبيانات الاتصال النشطة.
4. ملفات master data المذكورة في Gate 5، مع مالك لكل ملف وتاريخ قطع.
5. اعتماد محاسب للضرائب والرسوم وopening balances.
6. مفاتيح الخدمات اللازمة عبر قناة أسرار آمنة فقط: payment، WhatsApp، email، AI، error tracking.
7. قرار retention/privacy والشروط التي ستظهر للضيف.
8. تحديد ممثل UAT من التشغيل وموظف مالية وصاحب قرار Go/No-Go.

## 9. توزيع التنفيذ بين Codex وClaude

هذه الخطة تستخدم الوكيلين كمنفذين ومراجعين بالتبادل، وليس كمنفذين يغيران الملفات نفسها في الوقت نفسه.

### الملكية الأساسية

| الحزمة | المنفذ | المراجع المستقل | النطاق المملوك |
|---|---|---|---|
| CL-01 الشات بوت الحالي | Claude | Codex | `backend/app/modules/chat/**` واختباراته وملفات chatbot التي بدأها في موقع التسويق |
| CL-02 فصل وأمن موقع التسويق | Claude | Codex | public API client، Service Worker، consent، contact UI، marketing routes |
| CL-03 حقيقة المحتوى وSEO | Claude | Codex | المحتوى العام، JSON-LD، sitemap، اللغتان، دون اعتماد معلومة نهائية بنفسه |
| CL-04 جودة موقع التسويق | Claude | Codex | tests، a11y، performance، dependencies الخاصة بالموقع |
| CX-01 baseline ومراجعة دمج الشات | Codex | Claude | مراجعة diff، العقود، الاختبارات، single Alembic head |
| CX-02 صلاحيات وفروع PMS | Codex | Claude | auth/permissions/PMS، migration العضويات، اختبارات العزل |
| CX-03 تطبيق الموظفين وQR/PWA | Codex | Claude | `frontend/apps/el-kheima` وعقد public URL/cache |
| CX-04 بيانات الإنتاج والاستيراد | Codex | Claude | bootstrap/import/staging/audit/reconciliation |
| CX-05 CI/CD وDocker وVPS | Codex | Claude | compose، images، CI، backup/restore، hardening، Hostinger MCP |
| CX-06 Staging وcutover | Codex | Claude + المالك | DNS/TLS/deploy/smoke/rollback/monitoring |

### ملفات التماس التي لا تُعدل بالتوازي

الملفات التالية تنتقل ملكيتها بتسليم صريح لأنها قد يحتاجها المساران:

- `backend/app/main.py`
- `backend/app/core/config.py`
- `backend/app/core/rate_limit.py`
- `backend/.env.example`
- `backend/alembic/env.py` و`backend/alembic/versions/**`
- عقود `/api/v1/public/**`
- `docker-compose.prod.yml` وملفات Nginx

Claude يملك الملفات التي عدلها بالفعل حتى إغلاق CL-01. بعد تسليمه SHA/diff والاختبارات، تصبح migrations وملفات الربط المشتركة تحت ملكية Codex للحزم التالية. أي عودة من Claude إلى ملف مشترك تتطلب تحديث لوحة التنفيذ أولًا.

### دورة كل حزمة

1. **Claim:** المنفذ يضع الحزمة `IN_PROGRESS` ويكتب base SHA، الفرع/worktree، والملفات المتوقعة.
2. **Contract:** تثبيت API/schema/invariants ومعايير القبول قبل الكود.
3. **Implement:** تغيير نطاق واحد فقط وتشغيل الاختبارات المستهدفة.
4. **Handoff:** كتابة SHA أو diff، الملفات، migrations، أوامر الاختبار ونتائجها، والمخاطر المتبقية.
5. **Independent review:** الوكيل الآخر يراجع فقط ولا يعدل أثناء المراجعة.
6. **Remediation:** المنفذ الأصلي يصلح النتائج المقبولة.
7. **Gate:** لا تنتقل الحزمة إلى `DONE` إلا بعد صفر Critical/High، نجاح الاختبارات، وتحديث لوحة التنفيذ.
8. **Integrate:** Codex كمسؤول تكامل يراجع ترتيب الدمج وsingle migration head، لكن المالك يظل صاحب الموافقة على commit/push أو أي إجراء إنتاجي غير قابل للرجوع.

### ترتيب يسمح بالسرعة دون تضارب

```text
Claude CL-01 (إنهاء الشات الحالي)
               ↓ handoff
Codex CX-01 (مراجعة وGate 0)
               ↓
┌──────────────────────────────┬──────────────────────────────┐
│ Codex CX-02 صلاحيات/فروع     │ Claude CL-02 موقع التسويق    │
│ ثم CX-03 تطبيق الموظفين      │ ثم CL-03 محتوى وSEO          │
└──────────────────────────────┴──────────────────────────────┘
               ↓ عقود مستقرة ومراجعات متبادلة
Codex CX-04 بيانات الإنتاج + Claude CL-04 جودة الموقع
               ↓
Codex CX-05 VPS/CI/CD
               ↓
CX-06 Staging/UAT/Cutover بمراجعة Claude واعتماد المالك
```

### فروع وWorktrees

بعد حفظ عمل Claude الحالي في commit مراجَع:

- integration branch: `integration/el-kheima-production`
- Codex: worktree وفرع باسم `codex/<packet-id>-<slug>`
- Claude: worktree وفرع باسم `claude/<packet-id>-<slug>`
- موقع التسويق له الفروع المناظرة داخل مستودعه المستقل.

لا ننشئ worktrees من الحالة المتسخة الحالية، ولا ننقل تغييرات غير committed تلقائيًا. مراجعة diff غير committed تتم في worktree المنفذ نفسه وبوضع review-only.

### مصدر الحقيقة التشغيلي

- لوحة التنفيذ: `docs/agent-workflow/EL_KHEIMA_EXECUTION_BOARD.md`
- البروتوكول: `docs/agent-workflow/DUAL_AGENT_EXECUTION_PROTOCOL_AR.md`
- الخطة المرجعية: هذه الوثيقة.
- كل وكيل يبدأ جلسته بقراءة الملفات الثلاثة و`AGENTS.md`/`CLAUDE.md`، ثم `git status`, branch, HEAD, worktrees.
- لا يعتمد أي وكيل على رسالة محادثة قديمة لمعرفة الحالة؛ Git واللوحة وملف التسليم هي المصدر.

## 10. المصادر الرسمية المستخدمة للبيانات المتغيرة

- [Hostinger API Reference](https://developers.hostinger.com/)
- [Hostinger API MCP Server](https://www.hostinger.com/support/11079316-hostinger-api-mcp-server/)
- [Hostinger MCP Server repository](https://github.com/hostinger/api-mcp-server)
- [Hostinger VPS backup and restore](https://support.hostinger.com/en/articles/1583232-how-to-back-up-or-restore-a-vps)
- [El Kheima Beach Resort contact page](https://www.elkheimabeachresort.com/contact/)
- [Egyptian Tax Authority — VAT for specified tourist restaurants and cafés](https://www.eta.gov.eg/ar/news/twdh-khdw-almtam-walkafyhat-almhddt-bqrarat-wzyr-almalyt-ldrybt-alqymt-almdaft)
- [National Organization for Social Insurance — 2026 contribution limits](https://www.nosi.gov.eg/ar/News/Pages/2025-11-30.aspx)
- [Google Search — Review snippet structured data](https://developers.google.com/search/docs/appearance/structured-data/review-snippet)
- [MDN — Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy)
