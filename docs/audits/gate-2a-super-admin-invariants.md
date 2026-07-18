# Gate 2A — Super Admin Invariants: Plan + Implementation Record

**الحالة (2026-07-18): مُعتمَدة نهائيًا من Codex.** صحّحت 3 ملاحظات من أول
مراجعة (2 Medium + 1 Low، صفر Critical/High)، ثم اجتازت مراجعة اعتماد
نهائية بدون أي ملاحظة جديدة. **تم عمل checkpoint** (commitين منظمين على
فرع `gate-2a-super-admin-invariants`)، بدون push. لا تعتبر هذه الشريحة
إغلاقًا لـGate 2 بالكامل — راجع القسم 7 "خارج النطاق عمدًا" لما لسه لم
يُلمَس (Gate 2B التالية)، وراجع القسم 9 لتفاصيل تصحيحات المراجعة
والقسم 10 لسجل الاعتماد النهائي.

## 0. السياق

بعد اعتماد Gate 1B (Financial Atomicity — شريحة دفع Dining) بعد 3 جولات
مراجعة Codex، طلب محمد قراءة/تخطيط فقط لـ Gate 2 (Super Admin Backend
Safeguards) استنادًا لـ `docs/decisions/0003-super-admin-control-plane.md`.
التقرير الأول (قراءة فقط، بدون أي تعديل) حدّد 10 فجوات (G1–G10، Critical
إلى Low) واقترح شريحة أولى صغيرة (G1–G4). راجع محمد التقرير عبر Codex
وصحّح 4 نقاط قبل التنفيذ — التصحيحات موثّقة في القسم 2 تحت، وهي التي
حكمت التنفيذ الفعلي، مش المقترح الأول الخام.

## 1. الفجوات المُغطاة في هذه الشريحة (Gate 2A)

| # | الفجوة | Decision 0003 |
|---|---|---|
| G1 | منع صريح (`UserPermission.allowed=False`) كان يقدر يُسقط صلاحية `super_admin` فعليًا | invariant #1 |
| G2 | مفيش رفض لإنشاء `UserPermission` يستهدف `super_admin` | invariant #2 |
| G3 | مفيش حماية "آخر super_admin نشط" | invariant #4 |
| G4 | مفيش منع self-demotion/self-deactivation الروتيني | invariant #3 |

`change_password` bypass (G6 في التقرير الأول) **مؤجَّل صراحةً لـGate 2B**
منفصلة — نطاقان أمنيان مختلفان، قرار محمد صريح بعدم الخلط.

## 2. تصحيحات محمد على التقرير الأول (2026-07-18، عبر مراجعة Codex على الخطة)

قبل أي تنفيذ، رجّع محمد 4 تصحيحات إلزامية غيّرت التصميم الفعلي:

1. **`get_effective_permissions()` كانت بتكرر منطق الـdeny بدل استخدام
   `has_permission()`** — لو أصلحنا `has_permission()` بس، `/permissions/me`
   كان هيفضل يعرض بيانات مضلّلة لـsuper_admin (منع صريح ظاهر كـ`allowed:
   false` رغم إنه فعليًا inert على أي endpoint حقيقي). الحل: دالة قرار
   مركزية واحدة (`_resolve_permission`) الاتنين بينادوا عليها.
2. **HTTP mapping غلط**: منح الصلاحية (`POST /permissions`) ماكانش بيمسك
   `ValueError` خالص (أي خطأ مستقبلي كان هيهرب كـ500 عبر
   `SecureErrorMiddleware`)، وتعديل الدور (`PATCH /users/{id}/role`) كان
   بيحوّل **كل** `ValueError` لـ404 — يعني أي رفض invariant جديد (409
   بطبيعته) كان هيظهر غلط كـ"غير موجود".
3. **قفل super_admin لازم يكون بترتيب IDs ثابت** (منع deadlock) **مع
   إعادة تحقق إن المنفّذ نفسه لسه super_admin نشط تحت القفل** — مش بس
   يعتمد على فحص `get_super_admin_user` في بداية الـrequest (ده ممكن
   يبقى قديم لحظة التنفيذ الفعلي تحت تزامن حقيقي).
4. **`change_password` bypass (G6) حقيقي لكنه Gate 2B منفصلة** — نطاق
   أمني مختلف (step-up/session)، مش يُخلَط مع ثوابت الأدوار/الصلاحيات هنا.

## 3. التنفيذ الفعلي

### 3.1 — `_resolve_permission()` (جديد) + `has_permission()` +
`get_effective_permissions()` — `app/modules/core/services.py`

قرار مركزي واحد بدل تكرار المنطق مرتين (تصحيح محمد #1):

```
1) super_admin نشط (role=="super_admin" and is_active) → True دايمًا،
   source="super_admin" — أي UserPermission صريح موجود يفضل في
   الداتابيز (مش بيتحذف تلقائيًا) لكنه inert.
2) super_admin غير نشط → ما بياخدش الاستثناء (دفاع في العمق — الحالة
   دي أصلاً مستحيلة توصل هنا عبر HTTP لأن get_current_active_user بيرفض
   is_active=False قبل كده، لكن الفحص الصريح موجود على مستوى service).
3) استثناء صريح موجود → هو الحاكم.
4) لا شيء → role_fallback.
```

`has_permission()` بترجع `bool` فقط (نفس التوقيع القديم، صفر breaking
change لأي caller حالي — `require_permission()` في `deps.py` متلمسناهوش
خالص). `get_effective_permissions()` بقت بتنادي نفس الدالة لكل صف في
`PERMISSION_CATALOG`، فـ`/permissions/me` بيعرض `source: "super_admin"`
على كل الصفوف لـsuper_admin نشط، بدل تكرار شجرة القرار بنفسه.

**اختبار وجود deny قديم يفضل موجود بدون حذف تلقائي**: `test_super_admin_invariants.py::TestActiveSuperAdminBypassesExplicitDeny::test_explicit_deny_stays_inert_for_active_super_admin_real_endpoint`
بيتحقق من الصف نفسه في الداتابيز بعد النجاح — لسه موجود، `allowed=False`
زي ما هو.

### 3.2 — `grant_permission()` — `app/modules/core/services.py`

بقت بتجيب المستخدم المستهدف أولاً (`crud.get_user`) قبل أي إنشاء:

- المستخدم مش موجود → `UserNotFoundError` (404).
- `target.role == "super_admin"` (نشط أو غير نشط، الاتنين) →
  `SuperAdminPermissionOverrideForbiddenError` (409)، رفض فوري بدون أي
  تعديل على الداتابيز، مع تحذير أمني منظم (`logger.warning`، بدون أسرار).
- غير كده: نفس السلوك القديم بالظبط (`upsert_user_permission` + audit).

`revoke_permission()` **متلمسناهوش خالص** — حذف/تنظيف override قديم
يستهدف super_admin يفضل مسموح عمدًا (تصحيح محمد: "اسمح بحذف override
قديم... لا تمنع revoke").

**فحص بيانات حقيقي قبل التنفيذ** (قراءة فقط، بدون حذف): query مباشر على
قاعدة بيانات التطوير المحلية (`resort_os`، منفذ 5436) كشف **صفر** صف
`UserPermission` يستهدف حساب `role='super_admin'` حاليًا — يعني إصلاح G1
لا يغيّر أي سلوك حي موجود فعليًا اليوم، والإصلاح احترازي بالكامل لهذه
البيئة تحديدًا.

### 3.3 — `update_user_role()` — إعادة كتابة كاملة معاملاتية

**الترتيب الثابت (منع deadlock، تصحيح محمد #3)**:

```
1. crud.lock_active_super_admins(db)
   SELECT * FROM users WHERE role='super_admin' AND is_active=true
   ORDER BY id FOR UPDATE  (blocking، مش NOWAIT — زي قفل الفوليو
   في Gate 1B: نتسلسل ونعيد تقييم الحالة، مش نترفض فورًا)
2. تحقق: updated_by ∈ الصفوف المقفولة → وإلا
   ActorSuperAdminPrivilegesChangedError (409)
3. crud.lock_user_for_update(db, user_id) — الهدف، بعد قفل المجموعة
   دايمًا (نفس الترتيب في كل استدعاء = صفر deadlock ممكن)
4. حساب final_role/final_is_active من الحالة الحالية + payload (مش
   payload وحده — قيمة None في الحقل تعني "من غير تغيير")
5. رفض self-demotion/self-deactivation الفعليين (updated_by == user_id
   وفيه تغيير حقيقي) → SuperAdminSelfLockoutForbiddenError (409)،
   بصرف النظر عن عدد الـsuper_admin الباقيين. no-op مسموح.
6. رفض أي تغيير هيسيب صفر super_admin نشط →
   LastActiveSuperAdminRequiredError (409)
7. التنفيذ + AuditLog(action="update_role", new_data=الحالة النهائية
   الفعلية) + revoke_user_tokens + commit كوحدة واحدة
```

**ملاحظة تصميمية مهمة، اتأكدت بالتحليل الرياضي المباشر + اختبار حقيقي**:
بما إن الممثّل (`updated_by`) لازم يكون عضو في مجموعة الـsuper_admin
النشطين المقفولة (خطوة 2 بتضمن كده)، فلو حجم المجموعة ≤ 1، العضو
الوحيد فيها **لازم** يكون `updated_by` نفسه — يعني `LastActiveSuperAdminRequiredError`
غير قابلة للوصول فعليًا **لهذا الـendpoint تحديدًا** إلا في حالة self
(واللي بيتغطى فعليًا وأولاً بـ`SuperAdminSelfLockoutForbiddenError` قبل
ما نوصل للفحص ده أصلاً — self-lockout مجموعة أشمل، غير مشروطة بعدد
الباقيين). الكود اتسيب موجود عمدًا كـdefense-in-depth ولإعادة الاستخدام
في endpoints مستقبلية (حذف مستخدم، bulk update، استيراد) اللي
Decision 0003 بيسميها صراحةً لكن Gate 2A **لا تلمسها** — مش dead code
عشوائي، قرار موثّق. الاختبار الحقيقي تحت تزامن (قسم 4) بيثبت إن الحماية
الفعلية اللي بتمنع "آخر super_admin" تختفي بيجي عمليًا عبر
`ActorSuperAdminPrivilegesChangedError` لهذه الشريحة، مش عبر
`LastActiveSuperAdminRequiredError`.

### 3.4 — `crud.py` — `lock_active_super_admins()` + `lock_user_for_update()`

نفس نمط `finance.crud.lock_folio_for_update` بالظبط (blocking، `.populate_existing()`
إجباري — CLAUDE.md §13 بند ⓫). `lock_active_super_admins()` بترتب
`ORDER BY id` صراحةً (منع deadlock). `lock_user_for_update()` آمنة حتى لو
الهدف أصلاً جزء من المجموعة المقفولة فوق (نفس الصف، نفس الـtransaction).

### 3.5 — Router — `app/modules/core/api/router.py`

`update_user_role` و`grant_user_permission` بقوا يمسكوا الـexceptions
الجديدة صراحةً (409 لكل ثوابت الأمان، 404 لـ`UserNotFoundError`) —
مطابق تمامًا لنمط Gate 1B في `dining/api/router.py`
(`{"error_code": ..., "message": ...}`).

**اكتشاف أثناء الاختبار**: الـkernel عنده `@app.exception_handler(404)`
عام (`app/core/kernel/errors.py`) بيفلطح **أي** 404 في التطبيق كله لنفس
الشكل الموحّد `{"success": false, "error_code": "not_found", "message":
<detail>}`، بيتجاهل أي `error_code` مخصص ممرّر جوه `HTTPException`'s
detail dict. ده سلوك عام موجود من قبل Gate 2A على مستوى التطبيق كله (كل
404 تاني في المشروع بيسلك كده بالفعل — اتأكد بمراجعة كل تستات 404
الموجودة، كلها بتفحص `status_code == 404` بس، مفيش أي واحد بيفحص
error_code مخصص). `UserNotFoundError` بالتالي بترمي `HTTPException(404,
str(exc))` (نص عادي، مش dict) — **مطابقة للسلوك العام الموجود فعلاً في كل
المشروع**، مش استثناء جديد. تعديل الهندلر العام نفسه خارج نطاق Gate 2A
(يأثر على كل endpoint في التطبيق).

## 4. التحقق تحت تزامن حقيقي (Postgres)

`tests/test_super_admin_concurrency.py`
(`SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL`، **منفصل عن**
`DINING_CONCURRENCY_TEST_ADMIN_URL` عمدًا — قاعدة بيانات مؤقتة معزولة
لكل تست، نفس نمط `test_dining_paid_concurrency.py` بالضبط).

**السيناريو المطلوب حرفيًا**: `super_admin` نشطان A وB، معاملتان متزامنتان
(`threading.Barrier`) — A تحاول تخفّض B، وB تحاول تخفّض A في نفس اللحظة.

**النتيجة الفعلية المُثبَتة (شُغّلت فعليًا، 2/2 ناجحة)**:
- معاملة واحدة بالظبط تنجح.
- المعاملة التانية ترفض بـ`ActorSuperAdminPrivilegesChangedError` (المتوقَّع
  رياضيًا لهذا السيناريو بالضبط — راجع قسم 3.3) — الاختبار بيقبل برضو
  `LastActiveSuperAdminRequiredError` دفاعًا (زي ما حدد محمد "أو").
- `super_admin` نشط واحد بالظبط يفضل في النهاية — Decision 0003 invariant
  #4 محفوظ فعليًا تحت تزامن حقيقي، مش نظريًا بس.
- `super_admin` تالت (خارج السباق تمامًا) يقدر يدير النظام عاديًا بعد ما
  السباق يخلص — مفيش أي أثر جانبي دائم من المعاملة الخاسرة.
- ترتيب القفل الثابت (`ORDER BY id`) اتأكد إنه بيمنع deadlock فعليًا —
  الاتنين threads خلصوا خلال المهلة (`is_alive()` check)، صفر hang.

## 5. الاختبارات المضافة

- `tests/test_api/test_super_admin_invariants.py` — 15 اختبار (SQLite):
  bypass الـsuper_admin النشط على endpoint حقيقي (`require_permission`) +
  التأكد إن صف الـdeny القديم مش بيتحذف، `has_permission` مباشرة لحالة
  super_admin غير نشط، `/permissions/me` source="super_admin"، رفض
  `POST /permissions` على هدف super_admin نشط/غير نشط، 404 لهدف غير
  موجود، تأكيد إن السلوك العادي (هدف مش super_admin) سليم، تأكيد إن
  الحذف (تنظيف) لسه مسموح، self-lockout (role change + deactivation)،
  no-op مسموح، تأكيد إن الرفض المرفوض مبيلغيش التوكن، عقد الأخطاء
  (404/409)، AuditLog.new_data بيسجل الحالة النهائية الفعلية، وإثبات
  حتمي (single-threaded) لمسار "actor اتغيّرت صلاحيته بين المصادقة
  والتنفيذ".
- `tests/test_super_admin_concurrency.py` — 2 اختبار (Postgres-only،
  skip افتراضيًا): السباق الحقيقي المطلوب + تأكيد استمرار عمل النظام
  بعده.

**صفر اختبار موجود اتكسر أو اتضعف** — `test_permissions.py` (7 اختبار
قديم) و`test_deps_auth.py` (5 اختبار) عدّوا من غير أي تعديل عليهم.

## 6. نتائج التحقق الفعلية

```
pytest tests/ -v                → 1882 passed, 10 skipped, 0 failed
                                   (كان 1867 passed / 8 skipped قبل Gate
                                   2A — الفرق +15 passed بالظبط (ملف
                                   SQLite الجديد) + 2 skipped جدد
                                   (Postgres concurrency الجديد، skip
                                   افتراضيًا))
SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL=... pytest
  tests/test_super_admin_concurrency.py -v
                                → 2 passed (Postgres حي فعليًا، مش SQLite)
alembic heads                   → 9989c0432ccc (head واحد، بلا migration)
git diff --check                → نظيف
```

لم يُشغَّل `pnpm type-check:all`/`build:all` ولا فحص Docker Compose في
هذه الدفعة — **صفر ملف frontend أو deployment اتلمس** (نطاق Gate 2A
Backend-only بالكامل، مطابق للتعليمات).

## 7. خارج النطاق عمدًا (لم يُلمَس، ليس نسيانًا)

- `change_password` bypass لـadmin/super_admin (G6) — **Gate 2B منفصلة**،
  قرار محمد صريح.
- `LOGIN_2FA_ENFORCED` production fail-closed validator (G7).
- Recent-auth/step-up عام للعمليات الحساسة (G8).
- Typed settings registry (Decision 0003's settings ownership section).
- أي تعديل frontend (`PermissionsView.vue` لسه بتسمح للمستخدم يحاول
  يستهدف super_admin من القائمة — الرفض هيظهر كـtoast خطأ من الباك إند،
  مفيش أي تعديل UI في هذه الدفعة).
- أي migration.
- أي موديول غير Core/Auth (والاختبارات المرتبطة مباشرة).
- Project Cockpit — بيانات الـsnapshot **لم تُحدَّث** لتعكس Gate 2A؛
  الحالة تفضل "غير منفذ" في الكوكبيت لحد اعتماد Codex، عمدًا.

## 8. المخاطر المتبقية والخطوة التالية

- **G5 (سباق منفصل، حل جزئيًا كأثر جانبي)**: التقرير الأول ذكر "مفيش أي
  قفل/تزامن" كخطر مستقل — اتحل بالكامل كجزء من إعادة كتابة
  `update_user_role` (قسم 3.3)، مش خطر متبقٍ منفصل.
- **`LastActiveSuperAdminRequiredError` غير قابلة للوصول فعليًا عبر
  `update_user_role` وحدها** (راجع التحليل الرياضي، قسم 3.3) — قرار
  موثّق، مش خطأ. لو Gate 2B+ ضافت endpoint حذف/bulk-update مستخدم
  بمنطق مختلف (actor مش شرطًا عضو في المجموعة نفسها)، الفحص ده هيبقى
  فعليًا قابل للوصول وقتها.
- **`PermissionsView.vue`**: لسه بتعرض `super_admin` كخيار في قائمة
  الأدوار المستهدفة — محاولة المستخدم هتترفض من الباك إند بس (409)، لكن
  تجربة استخدام أنظف تحتاج فلترة الخيار ده من القائمة نفسها. مؤجَّل عمدًا
  (frontend خارج النطاق).
- **Gate 2B المقترحة (التالية)**: `change_password` step-up (G6) —
  الأولوية الأوضح لأنها ثغرة أمنية حقيقية موثّقة ومختبرة الغياب
  (صفر اختبار حالي على `/auth/change-password` خالص).

## 9. تصحيحات أول مراجعة Codex مستقلة (2026-07-18)

راجع Codex الـdiff والكود التشغيلي والاختبارات فعليًا (شغّل التستات
المستهدفة، اختباري Postgres الحقيقيين، `agent-check`، Alembic، Docker
Compose، `git diff --check`) بدل الاعتماد على تقرير Claude. القرار:
"تنفيذ Gate 2A الأساسي صحيح ومتين، لكن لسه محتاج تصحيحين قبل الاعتماد
النهائي. لا توجد ملاحظات Critical أو High." 3 ملاحظات:

### 9.1 — Medium: مسار قديم يتجاوز الحماية (`AuthService.update_user`)

`app/core/kernel/auth/service.py::AuthService.update_user` كان بيسمح
بتغيير `role`/`is_active` عبر `self.repo.update(user_id, data)` مباشرة —
مسار عام تمامًا بدون أي من ثوابت Gate 2A: مفيش قفل مرتّب لمجموعة
super_admin، مفيش فحص self-lockout، مفيش فحص last-active-super-admin،
ومفيش `AuditLog` — بس `revoke_user_tokens()` وحدها لو الصلاحية اتغيّرت.
البحث المباشر (`grep -rn "\.update_user(" app/`) أكّد **صفر caller حالي**
في المشروع كله — مش endpoint موصول، لكنه باب خلفي كامن لو استُدعي يومًا.

**الإصلاح**: الدالة بقت ترفض **أي** payload فيه `role` أو `is_active`
فورًا (403، `error_code: "USE_SUPER_ADMIN_CONTROL_PLANE"`) بغض النظر عن
`actor.role` — مش بس ترفض غير-super_admin زي الكود القديم. الرسالة
بتوجّه صراحةً لـ`PATCH /users/{id}/role` (المسار الرسمي المحمي).
الـfallback القديم (`privilege_change` + `revoke_user_tokens` بس، بدون
audit) اتشال بالكامل — بقى dead code فور ما role/is_active يستحيل
يوصلوا لـ`repo.update` من هنا. حقول تانية (زي `password`/`full_name`)
لسه شغالة عادي من غير أي تغيير.

**اختبار جديد**: `tests/test_api/test_auth_security_http.py::TestUpdateUserCannotBypassSuperAdminSafeguards`
(3 اختبار) — يثبت الرفض حتى لو الـactor نفسه super_admin (role change
+ deactivation)، والحالة الطبيعية (حقل عادي زي `full_name`) لسه شغالة.

### 9.2 — Medium: نجاح كاذب في اختبار Postgres الثاني

`tests/test_super_admin_concurrency.py::test_third_super_admin_can_still_demote_either_after_the_race`
كان فيه باج منطقي في اختيار الناجي بعد السباق: الشرط
`still_super_admin_id = a_id if outcome.get("y") == "ok" else b_id` معكوس
— لو `y` (B تخفّض A) نجحت، يبقى **A** هو اللي اتخفّض فعليًا وB هو
الناجي، لكن الكود كان بيختار `a_id` (الحساب المخفَّض بالفعل، بقى
`role="manager"` من الأساس). نتيجة ده: استدعاء
`update_user_role(target_id=a_id, role="manager", ...)` كان **no-op
حقيقي** (`role_changing=False` لأن الدور نفسه مش هيتغيّر) — الاختبار كان
بينجح من غير ما يختبر أي حاجة فعليًا، ومكانش فيه أصلاً أي assertion على
عدد/هوية super_admin النشطين قبل التصحيح.

**الإصلاح**:
- اختيار الناجي اتصحّح (`still_super_admin_id = a_id if outcome["x"][0] == "ok" else b_id`).
- اتضافت assertions صريحة: معاملة واحدة بالظبط تنجح والتانية تفشل، والفشل
  لازم يكون بسبب `ActorSuperAdminPrivilegesChangedError` أو
  `LastActiveSuperAdminRequiredError` تحديدًا (مش أي استثناء عشوائي).
- بعد ما C يخفّض الناجي الحقيقي، الاختبار بيتحقق صراحةً إن مجموعة
  super_admin النشطين في الداتابيز = `{c_id}` بالظبط — لا أكتر ولا أقل.

اتأكد الإصلاح فعليًا على Postgres حي (`SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL`):
2/2 ناجحين، النتيجة النهائية `{C}` فقط اتثبتت فعليًا.

### 9.3 — Low: تعليقات قديمة تتعارض مع الـsemantics الجديدة

4 ملفات كانت لسه فيها تعليقات/docstrings بتقول "الاستثناء الصريح بيكسب
الـrole دايمًا" من غير ذكر استثناء super_admin النشط الجديد — اتصحّحت
كلها لتوضّح القاعدة الحالية (super_admin نشط يعدّي أي منع صريح؛ باقي كل
المستخدمين يحكمهم الاستثناء الصريح لو موجود):

- `app/modules/core/models.py` — تعليق `UserPermission` model header.
- `app/core/deps.py` — docstring `require_permission()`.
- `app/modules/core/services.py` — تعليق قسم "Permission Matrix" فوق
  `_resolve_permission()`.
- `app/modules/core/schemas.py` — docstring/تعليق `EffectivePermission`
  (بما فيها قيمة `source` الجديدة `"super_admin"`).

### 9.4 — نتائج التحقق بعد التصحيحات الثلاثة

```
pytest tests/test_api/test_super_admin_invariants.py
       tests/test_api/test_permissions.py
       tests/test_api/test_core_http.py
       tests/test_api/test_auth_security_http.py
       tests/test_engines/test_deps_auth.py -v      → 98 passed
SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL=... pytest
  tests/test_super_admin_concurrency.py -v           → 2 passed (Postgres حي،
                                                         النتيجة النهائية {C} مؤكدة)
pytest tests/ -v                                     → 1885 passed, 10 skipped, 0 failed
                                                        (كان 1882/10 — +3 اختبار
                                                        جديد في test_auth_security_http.py)
alembic heads                                        → 9989c0432ccc (رأس واحد)
git diff --check                                     → نظيف
```

**صفر اختبار موجود اتكسر.** Project Cockpit لسه **لم يُلمَس** — الحالة
تفضل "غير منفذ/بانتظار اعتماد" لحد موافقة محمد النهائية.

## 10. اعتماد Codex النهائي (Acceptance Checkpoint، 2026-07-18)

مراجعة اعتماد نهائية قصيرة بعد تصحيحات القسم 9 لم ترجّع أي ملاحظة جديدة.
**القرار: Gate 2A معتمدة.**

Acceptance checkpoint نُفّذ كالتالي — صفر تغيير سلوك backend أو frontend
خارج تحديث الـsnapshot التطويري (Project Cockpit):

```
bash scripts/agent-check.sh                    → ناجح
pnpm --filter el-kheima type-check              → ناجح
pnpm --filter el-kheima build                   → ناجح
git diff --check                                → نظيف
```

commitين منظمين على فرع `gate-2a-super-admin-invariants` (staging
بمسارات محددة، مش `git add .`)، **بدون push**:

1. `fix(security): enforce super admin invariants` — كل تعديلات الباك
   إند (services/crud/router/deps/kernel auth service) والاختبارات.
2. `docs: record Gate 2A acceptance` — هذا الملف، `wagdy.md`،
   `PROJECT_STATUS.md`، وGate 2A cockpit snapshot data.

**Gate 2A مقفولة نهائيًا.** المرحلة التالية Gate 2B (`change_password`
step-up) على فرع مستقل جديد — يبدأ بتخطيط أمني فقط، بدون أي تنفيذ، وبدون
خلط مع commit/فرع Gate 2A.
