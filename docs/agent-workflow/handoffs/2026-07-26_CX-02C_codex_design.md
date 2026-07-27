# CX-02C — تصميم عضويات الفروع وعقد جلسة الموظف

**الحالة:** `DESIGN_READY / READ-ONLY INVENTORY`
**التاريخ:** 2026-07-26
**النطاق:** `resort-os`، وبالأخص Backend Core/Auth و
`frontend/apps/el-kheima` و`frontend/packages/core`
**تنفيذ كود أو migration:** لا
**Commit / Push / Deploy:** لا / لا / لا
**شرط بدء التنفيذ:** انتهاء تثبيت migration الخاصة بـCL-01R، ثم قراءة
`alembic heads` وإنشاء migration واحدة فوق الرأس الفعلي وقت التنفيذ.

---

## 1. القرار التنفيذي المختصر

التنفيذ الصحيح ليس إضافة `branch_id` إلى `User`، وليس استبدال الرقم `1`
برقم آخر. العقد المقترح هو:

1. `user_branch_memberships` هو مصدر حقيقة عضوية المستخدم في الفروع.
2. `is_default` داخل العضوية يحدد فرع البداية المعتاد للمستخدم.
3. `active_branch_id` يخص **جلسة الدخول الحالية**، ويخزن على عائلة
   `RefreshToken` الحية؛ لا يخزن عالميًا على `User`.
4. Backend يعيد bootstrap واحدًا يحتوي المستخدم والفروع المسموحة والفرع
   الافتراضي والنشط والصلاحيات الفعلية في الفرع النشط.
5. كل عملية داخلية مقيدة بفرع يجب أن تطابق الفرع النشط الذي اشتقه السيرفر؛
   العضوية وحدها لا تسمح بإرسال `branch_id` مختلف دون تنفيذ branch switch أولًا.
6. `super_admin` يظل عالميًا وفق Decision 0003، لكن لا يُعطى رقم فرع افتراضي
   وهمي. إذا كان هناك فرع نشط واحد فقط يختاره السيرفر، وإذا تعددت الفروع ولم
   يوجد default صريح تظهر شاشة اختيار.
7. الواجهة لا تقرأ `user.branch_id` ولا تستخدم `?? 1`. لا تُركّب الـrouter
   قبل اكتمال bootstrap.
8. Offline queue تشتق الفرع من bootstrap، وتفصل السجلات بـ
   `(owner_user_id, active_branch_id, module)`؛ سجلات ما قبل العقد الجديد
   تُحجر ولا تُرسل آليًا.
9. يبقى `Employee.branch_id` موجودًا كحقل HR وفرع وظيفي، ويُملأ منه backfill،
   لكنه يتوقف عن كونه مصدر authorization. لا حذف أو تغيير هدّام له في CX-02C.

هذا التصميم يمنع خطأين لا يحلهما جدول العضوية وحده:

- جهازان لنفس المدير يعملان في فرعين مختلفين دون أن يغير أحدهما سياق الآخر.
- إرسال طلب offline قديم لفرع A بعد أن أصبحت جلسة الموظف على فرع B.

---

## 2. الأدلة من التنفيذ الحالي

### 2.1 Backend

- `User` في `backend/app/core/kernel/models/user.py` لا يحتوي أي فرع.
- `UserRead` في `backend/app/modules/core/schemas.py` لا يعيد `branch_id`.
- `GET /api/v1/auth/me` في `backend/app/core/me_router.py` يعيد
  `UserRead` فقط؛ لا يعيد فروعًا أو صلاحيات أو سياقًا تشغيليًا.
- المصدر الحالي الوحيد لفرع المستخدم هو
  `Employee.user_id -> Employee.branch_id`. الحقل `Employee.user_id` فريد،
  ولذلك لا يمكنه تمثيل مستخدم يعمل في أكثر من فرع.
- `get_user_branch_id()` و`assert_branch_access()` في
  `backend/app/modules/core/services.py` يقرآن `Employee`.
- `_resolve_permission()` صار يطبق الصلاحيات المقيدة بالفرع، لكنه يستنتج
  الفرع من Employee عندما لا يُمرر branch صريح.
- `/permissions/me` موجود، لكنه نداء مستقل ولا يتم تحميله في auth store.
- جلسات HTTP الحالية لها `sid` مربوط بعائلة refresh token، ويعاد التحقق من
  بقاء العائلة حية في كل request. هذه هي البنية المناسبة لحفظ الفرع النشط
  لكل جلسة.
- PIN switch يصدر access token بلا `sid` ولا refresh family. يجب أن يحمل
  فرع terminal الحالي بعد تحقق عضوية المستخدم الهدف، وألا يختار فرعًا آخر
  تلقائيًا.
- CX-02B يحمي PMS وWebSocket ويفشل مغلقًا، لكنه containment أحادي الفرع
  مبني على Employee، وليس عقد multi-branch نهائيًا.

### 2.2 Frontend

- النوع `User` في `frontend/packages/core/src/types/index.ts` يدّعي أن
  `branch_id: number` إجباري رغم أن Backend لا يعيده.
- `frontend/packages/core/src/stores/auth.ts` يحتوي:

  ```ts
  user.value?.branch_id ?? 1
  ```

- fallbacks إضافية للرقم `1` موجودة في:
  - `components/ShiftPanel.vue`
  - `views/pos/ShiftMonitorView.vue`
  - `views/pos/ShiftDashboardView.vue`
  - `views/pos/BeachMapView.vue`
  - `views/admin/FinanceView.vue`
- `GuestAlertsBell.vue` يستخدم `?? 0` كحارس تعطيل، لكنه يظل دليلًا على عدم
  وجود عقد branch جاهز.
- هناك 36 ملفًا داخل تطبيق الموظفين يقرأ `auth.branchId`، و38 ملف view/
  component/layout يرسل `branch_id` أو يستخدمه.
- عدد كبير من الشاشات يلتقط `const branchId = auth.branchId` وقت mount،
  وبالتالي branch switch داخل SPA بدون teardown قد يبقي WebSockets وطلبات
  ومراجع قديمة للفرع السابق.
- router ينتظر `initAuth()` قبل التركيب، وهذه نقطة إدماج مناسبة للـbootstrap،
  لكنه يتحقق من الدور فقط ولا يحمّل effective permissions.

### 2.3 Offline queue

- IndexedDB حاليًا عند version 2.
- السجل يحفظ `ownerUserId` و`branchId`، وهي حماية جيدة من تبديل الموظف.
- `branchId` يأتي من caller، وليس من سياق جلسة server-validated.
- العد والمزامنة يفلتران بـowner وmodule فقط، وليس بالفرع.
- لذلك سجل فرع A قد يُرسل أثناء نشاط الجلسة على B. رد 4xx الحالي يُسجل
  `invalid_request` ثم يحذف السجل؛ أي رفض بسبب اختلاف branch قد يتحول إلى
  فقدان عملية صحيحة كان يجب إرسالها بعد الرجوع إلى A.

### 2.4 بيانات قاعدة التطوير المقروءة دون تعديل

الفحص التجميعي الحالي أعطى:

```text
users_total = 12
linked_users = 10
unlinked_users = 2
unlinked_roles = admin:1, super_admin:1
linked_to_inactive_branch = 0
active branches = WSR-001, BUGTEST1, BUGTEST2
```

الفرعان `BUGTEST1/BUGTEST2` يبدوان بقايا اختبارات ملتزمة في قاعدة التطوير.
لا يجوز للمigration حذفهما أو افتراض أنهما غير حقيقيين. يعرضهما تقرير
preflight ليقرر المشغل تنظيفهما بأداة منفصلة قبل staging.

نتيجة ذلك:

- الـadmin غير المرتبط يجب أن يفشل مغلقًا بعد cutover حتى تُنشأ له عضوية.
- الـsuper_admin يبقى عالميًا، لكن مع ثلاثة فروع نشطة لا يجوز اختيار أقل ID
  أو `1` له بصمت.

### 2.5 Baseline المقروء

```text
git branch: main
HEAD: 27cc217
working tree: dirty بسبب CX-02A/B/CX-03 وCL-01R
pytest collection: 2199
alembic head: dc6bfb5b79e8
dev compose config: PASS
prod compose config: FAIL فقط لأن PUBLIC_SITE_URL غير مضبوط
git diff --check: PASS
```

`dc6bfb5b79e8` معلومة وقت التصميم فقط، وليست down_revision يجب نسخها
مسبقًا. التنفيذ يقرأ الرأس من جديد بعد تحرير migration.

---

## 3. نموذج البيانات النهائي

### 3.1 جدول `user_branch_memberships`

```text
user_branch_memberships
  id                bigint/integer PK
  user_id           FK users.id, NOT NULL, ON DELETE CASCADE
  branch_id         FK branches.id, NOT NULL, ON DELETE CASCADE
  is_default        boolean NOT NULL DEFAULT false
  is_active         boolean NOT NULL DEFAULT true
  created_by        FK users.id, NULL, ON DELETE SET NULL
  revoked_at        timestamptz NULL
  revoked_by        FK users.id, NULL, ON DELETE SET NULL
  created_at        timestamptz NOT NULL DEFAULT now()
  updated_at        timestamptz NOT NULL DEFAULT now()
```

القيود والفهارس:

```text
UNIQUE (user_id, branch_id)
CHECK (NOT is_default OR is_active)
CHECK (
  (is_active = true  AND revoked_at IS NULL AND revoked_by IS NULL)
  OR
  (is_active = false AND revoked_at IS NOT NULL)
)
INDEX (user_id, is_active)
INDEX (branch_id, is_active)
PARTIAL UNIQUE (user_id)
  WHERE is_active = true AND is_default = true
```

ملاحظات:

- `created_by` يبقى NULL في backfill لأن العملية نظامية وليست فعل موظف.
- `revoked_by` يجوز أن يبقى NULL في migration/maintenance فقط؛ endpoint
  الإداري يملؤه دائمًا.
- إعادة التفعيل تستخدم نفس الصف: `is_active=true`, `revoked_at=null`,
  `revoked_by=null`. التاريخ التفصيلي محفوظ في `AuditLog`.
- لا يضاف `branch_role`. الدور الحالي عالمي على User، والاستثناءات الدقيقة
  موجودة أصلًا في `UserPermission.branch_id`. إضافة دور ثانٍ داخل العضوية
  ستخلق محركي authorization متعارضين.
- نشاط العضوية لا يعني أن الفرع نفسه نشط؛ الخدمة تتحقق من
  `Branch.is_active` أيضًا.

### 3.2 امتداد `refresh_tokens`

إضافة:

```text
active_branch_id  FK branches.id NULL ON DELETE SET NULL
INDEX (user_id, family_public_id, active_branch_id)
```

كل successor في refresh rotation ينسخ `active_branch_id` من الصف الحي
السابق. branch switch يحدّث الصف الحي غير المستهلك في العائلة الحالية فقط،
وليس كل جلسات المستخدم.

سبب عدم وضع الحقل على `User`:

- مدير قد يفتح فرع A على الكمبيوتر وفرع B على جهاز آخر.
- حقل على User يجعل آخر جهاز يبدّل الفرع لكل الأجهزة.
- default هو تفضيل حساب؛ active هو حالة session.

### 3.3 سياق PIN switch

توكن PIN بلا refresh session، ولذلك:

- PIN switch يستخرج active branch من جلسة terminal الحالية.
- يتحقق أن المستخدم الهدف عضو نشط في نفس الفرع وأن الفرع نشط.
- يصدر JWT قصير العمر يحمل claim اسمه مثلًا `bid`.
- `bid` لا يُوثق وحده؛ كل request يعيد التحقق من membership الحية.
- PIN session لا يسمح بتبديل الفرع. لتغيير الفرع يلزم full login/session
  ذات `sid`.
- PIN لمستخدم غير عضو في فرع terminal يرجع `403 PIN_BRANCH_MISMATCH`.

---

## 4. Migration وBackfill

### 4.1 ترتيب آمن

1. التأكد من انتهاء CL-01R وعدم وجود agent يعدل Alembic.
2. تشغيل:

   ```bash
   cd backend
   .venv/bin/alembic heads
   .venv/bin/alembic history --verbose
   ```

3. توليد **migration يدوية واحدة** فوق الرأس الفعلي.
4. إنشاء الجدول والقيود والفهارس.
5. إضافة `refresh_tokens.active_branch_id` nullable.
6. تنفيذ preflight queries وإخراج counts واضحة في تقرير التشغيل.
7. backfill العضويات من Employee.
8. backfill الفرع النشط للجلسات العادية حيث يوجد default صالح ووحيد.
9. عدم تحويل أي عمود إلى NOT NULL؛ الجلسة بلا branch حالة صريحة مدعومة.
10. اختبار upgrade/downgrade/upgrade على PostgreSQL معزول.

### 4.2 Preflight الإجباري

يُجمع ويُحفظ كartifact بلا PII غير ضرورية:

- عدد users النشطين حسب role.
- عدد users المرتبطين/غير المرتبطين بـEmployee.
- غير المرتبطين حسب role، مع IDs فقط في artifact المقيد.
- Employee مرتبط بفرع غير نشط.
- Employee مرتبط بمستخدم غير نشط أو soft-deleted.
- الفروع النشطة/غير النشطة وأكوادها.
- أي صفوف orphan؛ يفترض أن FK تمنعها.
- refresh families الحية التي لن تحصل على active branch.

الـmigration لا تخمن عضوية للمستخدم غير المرتبط، ولا تستخدم أول Branch.

### 4.3 Backfill

المبدأ:

```sql
INSERT INTO user_branch_memberships (
  user_id, branch_id, is_default, is_active,
  created_by, revoked_at, revoked_by, created_at, updated_at
)
SELECT
  employees.user_id,
  employees.branch_id,
  true,
  true,
  NULL,
  NULL,
  NULL,
  now(),
  now()
FROM employees
WHERE employees.user_id IS NOT NULL
ON CONFLICT (user_id, branch_id) DO NOTHING;
```

ثم:

- كل مستخدم backfilled له عضوية واحدة يحصل على default واحد.
- لا يُنشأ صف لـsuper_admin لمجرد أنه global.
- لا يُنشأ Employee وهمي للـadmin غير المرتبط.
- الجلسات الحية للمستخدمين أصحاب default وفرع نشط تحصل على
  `active_branch_id`.
- إذا كان default يشير لفرع غير نشط تبقى الجلسة `NULL` وتطلب اختيار/إصلاح.
- لو كان المستخدم super_admin ويوجد فرع نشط واحد فقط، bootstrap يمكن أن
  يختاره عند أول نداء؛ مع أكثر من فرع يرجع selection required.

### 4.4 التوافق والتراجع

- `Employee.branch_id` لا يُحذف ولا يُعاد تفسيره؛ يظل فرع ملف الموظف/الرواتب.
- أثناء CX-02C يصبح membership مصدر auth الوحيد بعد نجاح backfill.
- لا يعمل branch switch أو تغيير default على تحديث `Employee.branch_id`؛
  الأخير هو فرع HR/الرواتب التنظيمي، وتغييره كتأثير جانبي لتفضيل واجهة قد
  ينقل كشف راتب الموظف خطأ. التوافق هنا يعني إبقاء العمود وبياناته دون حذف،
  لا dual-write بين مفهومين مختلفين.
- downgrade يحذف `active_branch_id` وجدول العضويات. بعد بدء إدارة multi-branch
  يصبح downgrade فاقدًا للمعلومات التي لا يستطيع Employee تمثيلها، ولذلك هو
  maintenance-only ويتطلب backup/export. rollback الآمن بعد traffic هو إعادة
  نشر صورة التطبيق السابقة مع إبقاء schema الإضافية، لا downgrade فوري.

---

## 5. عقد الـAPI

### 5.1 Bootstrap

```http
GET /api/v1/auth/bootstrap
Authorization: Bearer <access token>
Cache-Control: no-store
```

الرد:

```json
{
  "contract_version": 1,
  "user": {
    "id": 12,
    "email": "employee@example.invalid",
    "full_name": "Employee",
    "role": "manager",
    "is_active": true,
    "two_factor_enabled": false,
    "must_change_password": false,
    "two_factor_bootstrap_required": false,
    "preferred_language": "ar",
    "created_at": "2026-07-26T00:00:00Z"
  },
  "branches": [
    {
      "id": 10,
      "code": "WSR-001",
      "name": "El Kheima Beach",
      "name_ar": "الخيمة بيتش",
      "timezone": "Africa/Cairo",
      "is_default": true
    }
  ],
  "allowed_branch_ids": [10],
  "default_branch_id": 10,
  "active_branch_id": 10,
  "requires_branch_selection": false,
  "effective_permissions": [
    {
      "resource": "pms.bookings",
      "action": "view",
      "allowed": true,
      "source": "role"
    }
  ]
}
```

قواعد:

- ordinary user يرى عضوياته النشطة في فروع نشطة فقط.
- super_admin يرى كل الفروع النشطة.
- إذا لا يوجد active صالح:
  - `active_branch_id=null`
  - `effective_permissions=[]` لغير super_admin
  - `requires_branch_selection=true` إذا توجد خيارات
  - إذا لا توجد خيارات: `requires_branch_selection=false` مع
    `BRANCH_MEMBERSHIP_REQUIRED` في حالة الواجهة.
- لا يستخدم `1` أو أول ID كfallback.
- endpoint يثبت default داخل refresh family عند أول نداء فقط إذا كان
  الاختيار غير ملتبس.
- `GET /auth/me` يبقى للتوافق وتفضيلات الحساب، لكنه لا يُستخدم لبناء تطبيق
  الموظفين بعد CX-02C.

### 5.2 تبديل الفرع

```http
PUT /api/v1/auth/active-branch
Authorization: Bearer <session-bound token with sid>
Content-Type: application/json

{"branch_id": 20}
```

النتيجة: نفس `AuthBootstrapRead` بعد التبديل.

التحقق:

1. access token صالح وsession family حية.
2. الفرع موجود ونشط.
3. ordinary user لديه membership نشطة.
4. super_admin يسمح له بأي Branch نشط.
5. قفل User أولًا بنفس ترتيب refresh rotation الحالي، ثم إعادة قراءة وقفل
   live refresh row وعمل UPDATE شرطي. هذا يسلسل switch مع refresh/revoke؛
   فلا ينسخ refresh متزامن الفرع القديم بعد نجاح switch.
6. AuditLog:
   - `action=active_branch_switched`
   - `entity_type=refresh_session`
   - `branch_id=new_branch_id`
   - old/new يحتويان IDs فقط وsession public ref؛ لا token/family secret.

الأخطاء:

```text
403 BRANCH_ACCESS_DENIED
403 BRANCH_INACTIVE
409 BRANCH_CONTEXT_REQUIRED
409 SESSION_CHANGED
422 validation error
```

لا يعاد `404` مختلف لمستخدم عادي بين فرع غير موجود وفرع غير مسموح حتى لا
يتحول المسار إلى branch enumeration oracle.

### 5.3 إدارة العضويات

مبدئيًا `super_admin` فقط + step-up + reason:

```http
GET    /api/v1/users/{user_id}/branch-memberships
PUT    /api/v1/users/{user_id}/branch-memberships/{branch_id}
DELETE /api/v1/users/{user_id}/branch-memberships/{branch_id}
PUT    /api/v1/users/{user_id}/default-branch/{branch_id}
```

عقد PUT:

```json
{"is_default": false, "reason": "Operational assignment"}
```

عقد DELETE:

```json
{"reason": "Transfer completed"}
```

يضاف purpose typed إلى step-up بدل dict حر:

```text
branch_membership_upsert
branch_membership_revoke
branch_membership_set_default
```

قواعد الخدمة:

- لا يمكن جعل inactive membership هي default.
- default جديد يلغي default القديم داخل transaction واحدة وتحت lock ثابت.
- إلغاء default يختار عضوية أخرى كdefault فقط إذا كان هناك اختيار وحيد؛
  وإلا يترك default null ويجبر اختيارًا إداريًا صريحًا.
- إلغاء عضوية يبطل active context لهذا الفرع في كل refresh families للمستخدم
  داخل نفس transaction. لا يلغي جلسات المستخدم السليمة في فروع أخرى؛
  access token ذو `sid` يقرأ السياق الحي من refresh row، وPIN token يعيد
  فحص membership، ولذلك لا تحتاج العملية إلى global logout لكل الأجهزة.
- كل upsert/revoke/default له AuditLog وسبب.
- عضوية super_admin لا تقيده ولا تغير global authority.

### 5.4 branch directory

المساران الحاليان `GET /branches` و`GET /branches/{id}` لا يبقيان كشفًا
عالميًا لأي حساب نشط:

- ordinary user يرى فقط الفروع الموجودة في bootstrap.
- super_admin يرى الكل.
- `PATCH /branches/{id}` يفرض active branch أو super_admin.
- إدارة إنشاء/تعطيل/حذف branch تظل عملية منفصلة عالية الخطورة؛ لا يوسع
  CX-02C صلاحياتها.

---

## 6. Enforcement داخل Backend

### 6.1 Resolver واحد

يضاف مفهوم `ResolvedAuthContext` داخلي:

```text
user
session_public_id | null
active_branch_id | null
authentication_mode = refresh_session | pin_session | legacy
```

- token مع `sid`: الفرع يأتي من live `RefreshToken.active_branch_id`.
- PIN token بلا `sid`: الفرع يأتي من signed `bid` ثم يُعاد التحقق من
  membership/Branch في DB.
- token قديم بلا `sid` ولا `bid`: auth العام يعمل مؤقتًا، لكن أي endpoint
  branch-scoped يرجع `409 BRANCH_CONTEXT_REQUIRED`.
- لا تُقبل branch claim دون DB lookup.

لخفض حجم التغيير مع الحفاظ على واجهة dependencies الحالية، يمكن ربط
`active_branch_id` كخاصية request-scoped غير mapped على User، لكن الأفضل
تقنيًا تعريف context typed وتمريره إلى dependencies الجديدة. ممنوع تخزينه
كعمود على User.

### 6.2 صلاحية الفرع

يستبدل `get_user_branch_id()` تدريجيًا بـ:

```text
get_allowed_branch_ids(db, user)
get_active_branch_id(auth_context)
assert_active_branch_access(db, auth_context, target_branch_id, action)
```

ordinary user يمر إذا:

```text
target_branch_id == auth_context.active_branch_id
AND membership(user, target_branch_id).is_active
AND branch.is_active
```

super_admin:

```text
branch exists AND branch.is_active
```

الوصول التشغيلي إلى فرع غير نشط مرفوض حتى للسوبر أدمن؛ إعادة تفعيله تتم من
control-plane وليس عبر endpoint تشغيل عادي.

### 6.3 Permission resolver

- `get_effective_permissions(db, user, branch_id=active_branch_id)` يصبح صريحًا.
- `require_permission()` يقيم branch-scoped override على active branch من
  auth context، لا على Employee.
- route يرفض target branch المختلف حتى لو كان المستخدم عضوًا فيه؛ يجب switch.
- branch-specific deny يسبق global grant وفق lookup الحالي.
- active super_admin يظل allowed لكل catalog.

### 6.4 حدود CX-02C

CX-02C يربط العقد الجديد بكل المواقع التي تستخدم اليوم
`assert_branch_access` وبكل PMS من CX-02B. لا يجوز اعتبار ذلك وحده إثبات أن
كل endpoint في الـ13 module صار معزولًا؛ يلزم scan مستقل لاحق لكل عقد يحمل
`branch_id`. أي endpoint غير مُرحّل يجب ألا يستعمل membership كادعاء حماية.

---

## 7. Frontend

### 7.1 Auth store

النوع الجديد:

```ts
interface AuthBootstrap {
  contract_version: 1
  user: User
  branches: AllowedBranch[]
  allowed_branch_ids: number[]
  default_branch_id: number | null
  active_branch_id: number | null
  requires_branch_selection: boolean
  effective_permissions: EffectivePermission[]
}
```

التغييرات:

- حذف `branch_id` من `User`.
- `branchId` يُشتق من `bootstrap.active_branch_id` ويكون `number | null`.
- إضافة `isBranchReady`, `allowedBranches`, `hasPermission()`.
- `login()`, `initAuth()`, `pinSwitch()` تحمل bootstrap كاملًا.
- أي failure في bootstrap يفشل مغلقًا؛ لا تركيب routes تشغيلية على user فقط.
- logout/401/PIN identity transition يمسح bootstrap والصلاحيات.

### 7.2 Boot وRouter

ترتيب `main.ts`:

```text
clear identity-bound caches
create Pinia/i18n
refresh access token
GET /auth/bootstrap
apply language
install router
mount
```

Route meta:

```ts
requiredPermission?: {
  resource: string
  action: string
}
```

الـguard:

1. auth.
2. temporary password.
3. mandatory 2FA.
4. branch selection قبل أي route تشغيلي.
5. role.
6. effective permission.

Backend يظل security boundary؛ guard UX فقط.

### 7.3 شاشة/مبدل الفرع

- route مستقلة `/select-branch`.
- تعرض allowed branches فقط.
- branch switch يستدعي PUT ثم يعمل **hard navigation/reload متعمدًا** إلى
  home route.

الـhard reload في هذه الحزمة اختيار أمان وتشغيل، لا workaround تجميلي:

- يغلق WebSockets للفرع القديم.
- يلغي timers وrequests ومراجع `const branchId = auth.branchId` القديمة.
- يعيد حساب route permissions والقوائم.
- يجعل offline queue تبدأ في scope جديد بوضوح.

يمكن لاحقًا تحويل التطبيق كله إلى reactive refs دون reload في حزمة UX مستقلة.

### 7.4 إزالة fallbacks

يُحذف `?? 1` من auth store والملفات الخمسة المذكورة. كل component:

- إما لا يُركب قبل `isBranchReady`.
- أو يقبل `branchId: number` إجباريًا من parent جاهز.
- لا يرسل `undefined`, `0`, أو `1` كبديل.

كما تزال تعليقات Settings القديمة التي تقول إن branch الافتراضي 1.

---

## 8. Offline queue بالفرع

### 8.1 Contract جديد

لا يقبل `submitOrder(branchId, ...)` رقمًا من caller. يصبح:

```ts
submitOrder(payload, outletId?)
```

ويقرأ active branch من auth bootstrap. إذا لم يكن branch جاهزًا يرفض محليًا
ولا يكتب record.

شكل السجل الجديد:

```text
localId
ownerUserId
branchId
branchContextVersion = 1
module
outletId?
payload
createdAt
```

`SyncLogEntry` يحصل أيضًا على `branchId`.

### 8.2 IndexedDB v3

- bump من 2 إلى 3.
- index مركب:

  ```text
  [ownerUserId, branchId, module, createdAt]
  ```

- السجلات القديمة التي لا تحمل `branchContextVersion` تصبح
  `legacy_unverified` ولا تُرسل تلقائيًا، حتى لو كان `branchId=1`.
- ownerless legacy يظل quarantined كما في CX-03.
- قبل production، manager recovery/report يعرض count فقط ويسمح export/delete
  وفق قرار تشغيل؛ لا تنسبها تلقائيًا لموظف/فرع حالي.

### 8.3 المزامنة

اختيار السجلات:

```text
record.ownerUserId == auth.user.id
AND record.branchId == auth.activeBranchId
AND record.module == current module
AND record.branchContextVersion == 1
```

قبل كل request يعاد فحص tuple:

```text
(user_id, active_branch_id)
```

إذا تغير توقف الحلقة. رد `BRANCH_CONTEXT_REQUIRED`,
`BRANCH_ACCESS_DENIED`, أو `BRANCH_CONTEXT_MISMATCH` لا يحذف السجل؛ يوقف
المزامنة ويطلب refresh/switch. الرفض التجاري الحقيقي فقط هو الذي يذهب إلى
sync log حسب العقد الحالي.

عند switch إلى B:

- سجلات A تبقى كما هي ولا تظهر في count الخاص بـB.
- عند الرجوع إلى A تعود للظهور والمزامنة FIFO.

---

## 9. Threat model

| التهديد | الدفاع |
|---|---|
| تعديل `branch_id` يدويًا | target يجب أن يساوي active server context، وإلا 403 |
| استخدام JWT قديم بعد إلغاء عضوية | membership live lookup + مسح active branch من families + token revocation |
| جهاز يغيّر فرع جهاز آخر | active branch مخزن per refresh family، لا على User |
| session refresh يعيد الفرع القديم/يفقده | refresh rotation ينسخ active_branch_id ذرّيًا |
| PIN لموظف فرع آخر على نفس terminal | تحقق target membership في فرع terminal قبل إصدار token |
| claim `bid` مزور/قديم | توقيع JWT لا يكفي؛ membership وBranch يعاد فحصهما من DB |
| default مزدوج تحت concurrency | partial unique index + row locking ثابت |
| branch switch أثناء offline sync | scope tuple check + hard reload + branch-filtered queue |
| حذف سجل offline صحيح بسبب 403 branch | أخطاء branch لا تحذف record |
| سجلات v2 صنعت تحت fallback 1 | quarantine، لا auto-attribution أو auto-sync |
| super_admin يُحرم بمنع أو membership | global bypass محفوظ؛ membership لا تحد سلطة super_admin |
| inactive branch يستقبل تشغيلًا | branch.is_active شرط مستقل عن membership |
| كشف قائمة فروع المنتجع | ordinary bootstrap وbranch directory يعيدان allowed فقط |
| TOCTOU بين فحص العضوية والعملية | الطلب الحالي قد يكمل بعد authorization؛ الإلغاء يقطع كل الطلبات التالية. العمليات المالية تبقي أقفالها وتدقيقها الحاليين |

---

## 10. مصفوفة الاختبارات

### 10.1 Schema/Migration

- unique `(user, branch)`.
- default واحد active فقط؛ محاولتان متزامنتان على PostgreSQL لا تنتجان
  defaultين.
- inactive membership لا تكون default.
- revoke consistency check.
- حذف user/branch يطبق قواعد FK المتفق عليها.
- backfill لمستخدم Employee واحد.
- المستخدم بلا Employee لا يحصل على عضوية مخمنة.
- Employee على inactive Branch يظهر في التقرير ولا يحصل على active session.
- upgrade → data checks → downgrade → upgrade على PostgreSQL معزول.
- `alembic heads` رأس واحد.

### 10.2 API Matrix A/B

| الحالة | Active | Target | المتوقع |
|---|---:|---:|---|
| user عضو A فقط | A | A | نجاح وفق permission |
| user عضو A فقط | A | B | 403 |
| user عضو A+B | A | B قبل switch | 403 |
| user عضو A+B | B بعد switch | B | نجاح |
| user عضو A+B | B | A | 403 حتى switch |
| membership B revoked | B | B | request التالي مرفوض والسياق null |
| Branch B inactive | B | B | مرفوض |
| user بلا membership | null | A | fail closed |
| super_admin | A | B active | نجاح بلا كسر invariants |

### 10.3 Session isolation

- جهاز 1 لنفس user على A، جهاز 2 على B؛ bootstrap لكل جهاز مستقل.
- refresh لكل جهاز يحفظ فرعه.
- switch جهاز 1 لا يغير جهاز 2.
- revoke membership B يبطل سياق الجهاز 2 فقط من ناحية branch، مع cutoff
  أمني لكل access tokens حسب قرار الخدمة.
- logout/revoke family يمنع branch switch على family ميتة.
- token قديم بلا sid/bid يستطيع `/auth/me` مؤقتًا لكنه لا يصل لأي endpoint
  branch-scoped.

### 10.4 Permissions

- branch grant في A يعمل في A فقط.
- branch deny في A لا يؤثر في B إلا إذا له صف B/global.
- global deny/grant يحافظ على الأولوية الحالية.
- active super_admin دائمًا allowed.
- bootstrap permissions تطابق dependency الفعلية لنفس active branch.
- route `requiredPermission` يخفي/يرفض UX، والنداء المباشر يظل Backend محميًا.

### 10.5 PMS/Object/WebSocket

إعادة تشغيل مصفوفة CX-02B بعد استبدال Employee بالمembership:

- list/read/mutate A/B.
- booking/room/rate-plan/housekeeping/night audit.
- cross-branch relationship rejects.
- WS A يعمل، WS B يغلق `4403` قبل switch، ثم العكس بعد switch.
- super_admin cross-branch.

### 10.6 PIN

- target عضو في فرع terminal ينجح ويحمل branch context.
- target غير عضو يرفض.
- membership revoked بعد إصدار PIN token يرفض request التالي.
- PIN token لا ينفذ branch switch.
- identity/branch change لا يرسل queue موظف سابق أو فرع سابق.

### 10.7 Frontend/Offline

- لا `?? 1` أو `user.branch_id` في staff app/core.
- لا mount لمسار تشغيلي قبل bootstrap.
- no-membership وmultiple-choice states بالعربي والإنجليزي.
- branch switch hard reload بعد نجاح السيرفر فقط.
- route meta permission fail closed للresource/action غير المعروف.
- queue record يظهر فقط لنفس user+branch+module.
- سجلات A لا تظهر/تتزامن في B.
- legacy ownerless وlegacy unverified محجورة.
- branch-context 403 لا يحذف السجل.
- PIN/user/branch transition يوقف sync loop.

### 10.8 أوامر التحقق

```bash
cd backend
.venv/bin/pytest -v \
  tests/test_api/test_branch_memberships_http.py \
  tests/test_api/test_auth_branch_bootstrap.py \
  tests/test_api/test_pms_branch_isolation_http.py \
  tests/test_api/test_pms_permissions_http.py \
  tests/test_permissions.py \
  tests/test_api/test_core_http.py \
  tests/test_api/test_auth_sessions_and_audit.py
.venv/bin/pytest tests/ -v
.venv/bin/alembic heads

cd ../frontend
pnpm --filter el-kheima test:frontend
pnpm --filter el-kheima type-check
pnpm --filter el-kheima build

cd ..
git diff --check
docker compose config --quiet
PUBLIC_SITE_URL=https://staging.example.invalid \
  docker compose -f docker-compose.prod.yml config --quiet
```

PostgreSQL concurrency/migration tests لا تُستبدل بـSQLite.

---

## 11. ملكية الملفات المقترحة وقت التنفيذ

### Backend CX-02C

```text
backend/app/modules/core/models.py
backend/app/modules/core/schemas.py
backend/app/modules/core/crud.py
backend/app/modules/core/services.py
backend/app/modules/core/api/router.py
backend/app/core/me_router.py
backend/app/core/deps.py
backend/app/core/kernel/models/user.py
backend/app/core/kernel/auth/service.py
backend/app/core/kernel/auth/router.py
backend/app/core/kernel/auth/step_up.py
backend/app/seed.py
backend/alembic/versions/<new_single_head>_user_branch_memberships.py
backend/tests/test_api/test_branch_memberships_http.py
backend/tests/test_api/test_auth_branch_bootstrap.py
backend/tests/test_api/test_pms_branch_isolation_http.py
backend/tests/test_api/test_pms_permissions_http.py
backend/tests/test_permissions.py
backend/tests/test_api/test_core_http.py
backend/tests/test_api/test_auth_sessions_and_audit.py
```

### Frontend CX-02C

```text
frontend/packages/core/src/types/index.ts
frontend/packages/core/src/api/endpoints.ts
frontend/packages/core/src/stores/auth.ts
frontend/packages/core/src/composables/useOfflineQueue.ts
frontend/apps/el-kheima/src/main.ts
frontend/apps/el-kheima/src/router/index.ts
frontend/apps/el-kheima/src/views/account/BranchSelectionView.vue
frontend/apps/el-kheima/src/components/BranchSwitcher.vue
frontend/apps/el-kheima/src/layouts/BackOfficeLayout.vue
frontend/apps/el-kheima/src/layouts/FieldLayout.vue
frontend/apps/el-kheima/src/components/ShiftPanel.vue
frontend/apps/el-kheima/src/components/GuestAlertsBell.vue
frontend/apps/el-kheima/src/views/pos/ShiftMonitorView.vue
frontend/apps/el-kheima/src/views/pos/ShiftDashboardView.vue
frontend/apps/el-kheima/src/views/pos/BeachMapView.vue
frontend/apps/el-kheima/src/views/pos/UnifiedPOSView.vue
frontend/apps/el-kheima/src/views/pos/BeachPOSView.vue
frontend/apps/el-kheima/src/views/admin/FinanceView.vue
frontend/apps/el-kheima/src/views/admin/SettingsView.vue
frontend/packages/core/src/i18n/locales/ar.json
frontend/packages/core/src/i18n/locales/en.json
frontend/apps/el-kheima/src/__tests__/security/authRoleGuard.spec.ts
frontend/apps/el-kheima/src/__tests__/pos/offlineQueueIdentity.spec.ts
frontend/apps/el-kheima/src/__tests__/auth/branchBootstrap.spec.ts
```

ملفات chat وmarketing وCL-01R ليست ضمن الملكية.

---

## 12. ترتيب التنفيذ فور تحرير migration

1. تجميد رأس Alembic وقراءة diff المتحرك.
2. إضافة model + migration + preflight/backfill، واختبار PostgreSQL cycle.
3. بناء CRUD/services للعضوية والdefault مع constraints واختبارات التزامن.
4. تمديد refresh family بالفرع النشط ونسخه في rotation.
5. بناء resolved auth context والـbootstrap/switch contracts.
6. تحويل `assert_branch_access` وpermission resolver من Employee إلى active
   membership context.
7. تحويل PMS/CX-02B وWebSockets وتشغيل A/B matrix.
8. إضافة admin membership endpoints + step-up + audit.
9. تحويل auth store وboot/router إلى bootstrap واحد، ثم شاشة اختيار الفرع.
10. حذف fallbacks والأنواع الكاذبة، وإضافة permission-aware route meta.
11. ترقية IndexedDB v3 وعزل queue user+branch+module وحجر legacy.
12. تشغيل targeted tests، ثم full Backend/Frontend/Compose gates.
13. مراجعة أمنية مستقلة قبل أي commit/push/deploy.

---

## 13. قرارات مطلوبة قبل production وليست مانعة لبدء الكود

1. تحديد ما إذا كان الـadmin غير المرتبط في البيانات الحالية يجب أن يحصل على
   عضوية `WSR-001` أم يبقى blocked. الآمن افتراضيًا: blocked.
2. مراجعة الفروع `BUGTEST1/BUGTEST2` وحذفها بأداة/قرار منفصل إذا تأكد أنها
   test residue؛ migration لا تحذفها.
3. تقرير إن كانت هناك terminals فعلية تحتوي IndexedDB v2. إن وجدت، نحتاج
   manager recovery/export UI قبل تفعيل auto-sync الجديد.
4. إدارة branch create/deactivate تحتاج لاحقًا step-up typed وعقد تأثير على
   البيانات؛ لا تُضمّن خلسة داخل CX-02C.

---

## 14. معايير قبول CX-02C

لا تعتبر الحزمة مكتملة إلا إذا:

- لا يوجد `branch_id ?? 1` أو `user.branch_id` في تطبيق الموظفين.
- ordinary user لا يصل إلا إلى active branch واحد في الجلسة، بعد عضوية حية.
- مستخدم متعدد الفروع يبدل server-side مع AuditLog.
- جهازان لنفس المستخدم يحتفظان بفرعين مختلفين.
- refresh وPIN وWebSocket تحافظ على نفس حدود الثقة.
- permission overrides تُقيّم على active branch الصحيح.
- offline records لا تنتقل بين مستخدمين أو فروع ولا تُحذف بسبب context mismatch.
- backfill لا يخمن مستخدمًا أو فرعًا.
- PostgreSQL يثبت default uniqueness والتزامن.
- Alembic له head واحد، full tests/type-check/build تمر، ولا commit/push/deploy
  دون طلب المالك.
