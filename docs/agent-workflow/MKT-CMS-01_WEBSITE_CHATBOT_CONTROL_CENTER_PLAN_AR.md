# MKT-CMS-01 — الخطة التنفيذية لمركز إدارة الموقع والشات بوت

> **حالة الوثيقة:** `DRAFT — OWNER APPROVAL REQUIRED`  
> **حالة التنفيذ:** `STOPPED / NOT AUTHORIZED`  
> **المالك وصاحب قرار البدء:** Mohamed  
> **قائد التنفيذ والمراجع النهائي المقترح:** Codex  
> **تاريخ إعداد الخطة:** 2026-08-01  
> **Resort OS baseline:** `ff8c61c` على
> `claude/CX-02C-frontend-auth-bootstrap`  
> **Marketing baseline:** `16f8f2c` على `main`  
> **الإنتاج الحالي:** Resort `a3e8abb`، Marketing `16f8f2c`

هذه وثيقة تنفيذ كاملة قابلة للتحويل إلى حزم عمل بعد اعتماد Mohamed، لكنها
**ليست إذنًا بالتنفيذ أو commit أو push أو deploy أو migration أو تعديل
بيانات أو أسعار أو Chatbot أو VPS**. تظل لوحة التنفيذ الحية
`EL_KHEIMA_EXECUTION_BOARD.md` هي مصدر المهمة الجارية، ولا تُضاف هذه الحزمة
إليها إلا بعد موافقة المالك الصريحة.

---

## 0. بوابات موافقة المالك

### Approval A — بدء التطوير

العبارة المقترحة للاعتماد:

> أوافق على بدء تنفيذ MKT-CMS-01 وفق الخطة، مع بقاء الأسعار الرقمية غير
> منشورة، ومن دون نشر إنتاجي قبل موافقتي المنفصلة.

هذه الموافقة تسمح فقط بـ:

- إنشاء task brief وحزمة عمل/Worktree مملوكة للمهمة.
- تنفيذ الكود والمهاجرات والاختبارات محليًا.
- إنشاء مسودات محتوى من البيانات الحالية.
- بناء Preview وUAT على بيئة غير إنتاجية أو في وضع غير منشور.

ولا تسمح بـ:

- تغيير `PUBLIC_TRUTH.publish.prices`.
- نشر سعر رقمي أو عرض أو موقع دقيق أو ادعاء غير معتمد.
- تشغيل migration أو importer على الإنتاج.
- بناء أو استبدال حاويات الإنتاج.
- تعديل DNS أو TLS أو أسرار Gemini أو بيانات حقيقية.

### Approval B — السماح بنشر أسعار رقمية

موافقة مستقلة لا تُستنتج من Approval A:

> أوافق على نشر الأسعار الرقمية للفئات المحددة في قرار البيانات المرفق،
> بعد نجاح مراجعة المالية والتشغيل واختبارات بوابة الحقيقة.

يجب أن تحدد الموافقة الفئات المسموح بها، ومصدر كل سعر، وتاريخ السريان.
إذا لم تصدر هذه الموافقة، تظل الأنماط العامة الوحيدة المسموحة:
`hidden` و`contact_for_price`، حتى لو كانت قيمة السعر محفوظة كمسودة.

### Approval C — النشر على الإنتاج

موافقة مستقلة بعد تسليم أدلة UAT:

> أوافق على نشر إصدار MKT-CMS-01 المحدد بالـcommit والـdigest المرفقين على
> الإنتاج، وفق خطة النسخ الاحتياطي والتراجع المراجعة.

أي عبارة عامة مثل «كمل» قبل عرض تقرير القبول لا تُعتبر تلقائيًا Approval B
أو C. عند الشك يتوقف التنفيذ ويطلب Codex تحديد الموافقة المطلوبة.

---

## 1. النتيجة التجارية المطلوبة

إنشاء مركز إدارة عربي/إنجليزي داخل `https://app.elkheima.com` يمكّن الإدارة
من التحكم الآمن في المحتوى العام لموقع `elkheima.com` والشات بوت، من دون
تعديل كود الموقع أو إعادة بناء Docker عند كل تغيير محتوى.

يجب أن يستطيع المستخدم المصرح له:

1. إنشاء وتعديل تفاصيل الأنشطة والفعاليات والباقات وخدمات الشاطئ والغرف
   والـTimeshare والخدمات التسويقية.
2. إدارة الاسم والوصف والمميزات والصور والترتيب والظهور بأربع لغات:
   العربية والإنجليزية والروسية والإيطالية.
3. اختيار سياسة السعر: مخفي، تواصل لمعرفة السعر، يبدأ من، أو ثابت.
4. إدارة الصور من مكتبة وسائط دائمة خارج إصدارات Docker.
5. تعديل بيانات التواصل والسوشيال ومواعيد العمل ومحتوى SEO المسموح.
6. إدارة تشغيل الشات بوت ورسائل الترحيب والحقائق والأسئلة الشائعة المعتمدة.
7. معاينة التغييرات قبل نشرها على الهاتف والكمبيوتر وبكل لغة.
8. نشر إصدار ذري واحد، مع Audit وStep-Up وسبب إلزامي.
9. الرجوع إلى الإصدار السابق من دون استرجاع قاعدة البيانات.

الهدف ليس إنشاء CMS عام أو Website Builder مفتوح؛ الهدف هو مركز تحكم
محدود ومهيكل يناسب صفحات El Kheima Beach الحالية ويقلل أخطاء المحتوى.

---

## 2. الأدلة الحالية التي بُنيت عليها الخطة

### 2.1 موقع التسويق

- الأنشطة والفعاليات والباقات وغيرها ما زالت مصفوفات ثابتة داخل ملفات Vue.
- `useMediaSettings` يحاول قراءة `/settings/public`، لكن Resort OS لا يملك
  هذا العقد العام، ثم يعود بصمت إلى القيم الثابتة.
- `usePageText` يقرأ override عربيًا أو إنجليزيًا فقط؛ الروسية والإيطالية
  تسقطان حاليًا إلى الإنجليزية في أي override ديناميكي.
- `VITE_CHATBOT_ENABLED` موجود كـbuild argument، لكن `App.vue` يعرض Widget
  من دون شرط تشغيل فعلي.
- `PUBLIC_TRUTH.publish.prices=false` يمنع الأسعار الرقمية، ويجب الحفاظ عليه
  حتى قرار مالك مؤرخ.
- الموقع مستقل عن Resort OS ولا يجوز استيراد packages أو source code منه؛
  التكامل الوحيد هو API عام مراجع.

### 2.2 Resort OS

- موديول `hub` يملك صفحات وعروضًا ومدونة وحجوزات ونماذج تواصل، وهو bounded
  context الصحيح لتوسيع إدارة الموقع.
- `HubPage` و`HubOffer` يدعمان العربية والإنجليزية فقط، ولا يملكان revision
  أو preview أو publication snapshot أو rollback.
- `HubPageRead` لا يعيد body/content، وendpoints الصفحات والعروض الحالية
  staff-authenticated؛ لذلك لا تمثل Public CMS API.
- `HubManagementView.vue` نواة صالحة للواجهة، لكنه يجمع الحجوزات والعروض
  والصفحات والمدونة والتواصل ولا يغطي Workflow إدارة موقع كامل.
- الأسعار الحالية في `HubOffer` تستخدم `Decimal/Numeric`، ويجب استمرار ذلك.
- `ChatPublicFact` يملك حالات `draft/approved/retired`، ومصدرًا وتاريخ اعتماد
  وانتهاء، وهو أساس آمن يجب تطويره بدل استبداله.
- الشات الحالي يبني الـprompt من الحقائق المعتمدة غير المنتهية فقط، ولا يخزن
  رسائل الضيوف الخام؛ هذان invariant لا يجوز كسرهما.

### 2.3 المشروع القديم المرجعي

المشروع `/home/wego/projects/elkheima-beach-resort` مرجع أفكار UX فقط:

**قابل للاستفادة كمفهوم:**

- تبويبات وتصنيف وبحث المنتجات.
- نموذج الاسم والوصف والصورة والسعر والتفعيل والتمييز.
- مكتبة الصور حسب الصفحة.
- محرر Q&A وقاعدة المعرفة ومحاكي الشات.
- ترتيب العناصر وFeatured/Active.

**ممنوع نسخه كتنفيذ:**

- تخزين إعدادات الموقع في `settings_override.json`.
- قبول dict عشوائي للإعدادات.
- خلط المحتوى والضرائب والصلاحيات والأسرار في مخزن واحد.
- استخدام `Float` للأموال.
- كتابة الصور داخل source tree أو Docker image.
- حفظ إعدادات وتحليلات الشات في `localStorage`.
- تعدد مصادر الحقيقة بين JSON وقاعدة البيانات وملفات i18n.
- إتاحة المحادثات أو إعدادات/معرفة الإدارة عبر endpoint عام.

---

## 3. القرارات الافتراضية المقترحة

تُعتبر البنود التالية هي الاختيارات الموصى بها عند Approval A، ما لم يعدلها
Mohamed صراحةً:

1. فرع تشغيلي واحد بلا Branch Switcher، مع استمرار العزل fail-closed.
2. توسيع `hub` الحالي؛ لا إنشاء CMS مستقل ولا خدمة Microservice جديدة.
3. الموقع المستقل يستهلك Public API فقط، ولا يعتمد على packages داخلية.
4. المحتوى الديناميكي بأربع لغات؛ لا نشر عنصر ناقص لغة مطلوبة.
5. موظف بصلاحية تحرير يحفظ Draft فقط؛ `super_admin` ينشر ويرجع الإصدارات.
6. نشر المحتوى أو السعر يحتاج Step-Up وسببًا مسجلًا.
7. الأسعار الرقمية تبقى غير منشورة في أول Release.
8. الأسرار ومفاتيح Gemini والنموذج وحدود التكلفة تبقى في بيئة الخادم.
9. لا حفظ لنصوص محادثات الضيوف الخام.
10. لا حذف فعلي لمحتوى أو صورة منشورة؛ يستخدم archive/retire ثم retention.
11. لا إعادة تصميم بصري شامل للموقع ضمن هذه الحزمة.
12. واجهة الموظفين تبقى عربية/إنجليزية؛ محتوى الضيف نفسه يدعم AR/EN/RU/IT.

---

## 4. نطاق النسخة الأولى

### 4.1 داخل النطاق

- Profile عام للعلامة والتواصل ومواعيد العمل والسوشيال.
- Home sections المحددة، Heroes وCTA الآمنة.
- أنشطة، فعاليات، باقات، خدمات شاطئ، فئات غرف، Restaurant highlights.
- وحدات/فئات Timeshare والنص المعتمد عن Blue Bay.
- FAQ وسياسات عامة مسموح نشرها.
- مكتبة صور مع variants وAlt Text.
- SEO title/description/Open Graph image للصفحات الموجودة.
- ترتيب وإظهار/إخفاء العناصر.
- Draft/Preview/Validate/Publish/Rollback.
- Runtime Chatbot enable switch ورسائل الترحيب والحقائق المعتمدة.
- Public snapshot API مع Cache وETag.
- Sitemap مبني من الإصدار المنشور.
- Audit وصلاحيات وStep-Up.
- استيراد المحتوى الثابت الحالي كمسودات قابلة للمراجعة.

### 4.2 خارج النطاق

- محرر Drag-and-Drop عام أو إنشاء layouts حرة.
- تجارة إلكترونية أو دفع أو تأكيد حجز تلقائي من محتوى التسويق.
- مزامنة أسعار خارجية مع Booking.com أو Channel Manager.
- تحرير أسرار أو system prompt أو أوامر خادم من الواجهة.
- نشر تقييمات أو ندرة أو عروض أو موقع دقيق قبل موافقة Public Truth مستقلة.
- تحويل Inventory إلى كتالوج عام؛ التكلفة والمورد والمخزون بيانات داخلية.
- تخزين أو عرض سجل المحادثة الخام.
- استيراد مباشر لقاعدة بيانات المشروع القديم.
- تعديل DNS أو TLS.
- إعادة كتابة صفحات الموقع كلها دفعة واحدة.

---

## 5. مصدر الحقيقة حسب نوع البيانات

| البيانات | مصدر الحقيقة | طريقة ظهورها في الموقع |
|---|---|---|
| أسعار وأصناف المطعم والكافيه التشغيلية | `dining` | Digital Hub يظل live؛ Marketing snapshot يختار Highlights فقط |
| سعر دخول وخدمات الشاطئ التشغيلية | `beach` + typed settings الحالية | يحلّه Backend عند بناء snapshot بعد الاعتماد |
| الغرف وخطط الأسعار | `pms` / rate plans | Snapshot تسويقي؛ لا استنتاج للتوفر من حالة الغرفة |
| التكلفة والمخزون والموردون | `inventory` | لا تُنشر للعامة مطلقًا |
| الأنشطة والفعاليات والباقات التسويقية | `hub` public catalog | تحرير ونشر من مركز الموقع |
| بيانات Timeshare التشغيلية والعقود | `timeshare` | لا تُنشر؛ Hub يعرض فقط وصفًا وفئات عامة معتمدة |
| Blue Bay والنصوص القانونية العامة | Hub content موثق بمصدر | يظهر بعد اعتماد المحتوى، بلا وعود تعاقدية |
| الهاتف/واتساب/البريد/المواعيد | Hub site profile typed | جزء من publication snapshot |
| حقائق الشات | publication snapshot + `ChatPublicFact` | approved locale facts فقط |
| مفاتيح Gemini والأسرار والميزانية | environment/secrets | لا تظهر ولا تتعدل من CMS |

لا يُنسخ السعر التشغيلي إلى حقل نص حر. إذا كان عنصر Hub مرتبطًا بموديول
تشغيلي، يخزن `source_module` و`source_entity_id`، ويحل Backend السعر الموثوق
أثناء Validate/Publish. التغيير التشغيلي بعد النشر يظهر كـdrift في لوحة
الإدارة ولا يغير السعر العام بصمت؛ يحتاج إصدار نشر جديد.

---

## 6. المعمارية المستهدفة

```text
app.elkheima.com
  Staff Control Center
        |
        | Auth + permission + branch + step-up
        v
Resort OS /api/v1/hub/*
  Authoring tables -> validation -> immutable publication snapshot
        |                              |
        |                              +-> approved chatbot facts
        |                              +-> sitemap / SEO snapshot
        v
  Persistent media volume

elkheima.com
  GET /api/v1/public/site/bootstrap?locale=ar
        |
        +-> published snapshot only + ETag
        +-> no draft / no branch_id from browser
        +-> safe static fallback on failure
```

### 6.1 مبدأ النشر

الموقع العام لا يقرأ جداول التحرير live. عملية النشر تبني Snapshot غير قابل
للتعديل يحتوي فقط البيانات التي اجتازت التحقق والبوابات، ثم تبدل
`current_publication_id` داخل transaction واحدة. هذا يضمن:

- عدم ظهور نصف تحديث.
- ثبات الأسعار والنصوص خلال الإصدار.
- rollback لحظي إلى snapshot سابق.
- cache key واضح بالـpublication version.
- قدرة الشات وSEO والموقع على استخدام نفس الحقائق.

### 6.2 فشل آمن

- Draft لا يدخل public snapshot.
- السعر غير المسموح لا يوضع في JSON العام أصلًا.
- إذا لم توجد ترجمة، يمنع النشر بدل نشر قيمة فارغة أو لغة خاطئة.
- إذا فشل Public API، يستخدم الموقع المحتوى الثابت الآمن الحالي، مع
  `contact_for_price` ومن دون ادعاءات غير معتمدة.
- إذا تعذر التحقق من Chat provider أو budget guard، يبقى الشات غير متاح.

---

## 7. نموذج البيانات المقترح

الأسماء نهائية فقط بعد قراءة migration history واختبار PostgreSQL، لكنها
تمثل العقد المطلوب.

### 7.1 `hub_site_profiles`

- `id`, `branch_id` unique.
- بيانات عامة typed: phone, WhatsApp, email, hours, social URLs.
- map/exact-location fields خلف truth gate.
- chatbot/runtime public switches غير السرية.
- `created_at`, `updated_at`, `updated_by`.

لا يقبل هذا الجدول key/value عشوائيًا.

### 7.2 `hub_catalog_items`

- `id`, `branch_id`, `slug`.
- `content_type`:
  `activity|event|package|beach_service|room_category|restaurant_highlight|timeshare_unit|general_service`.
- `status`: `draft|in_review|published|archived`.
- `is_visible`, `is_featured`, `sort_order`.
- `primary_media_id`.
- `price_mode`: `hidden|contact_for_price|from|fixed`.
- `manual_price Numeric(12,2)`, `currency`.
- `price_unit` مثل per_person/per_night/per_group، من enum مراجع.
- `source_module`, `source_entity_id` للربط الاختياري.
- `valid_from`, `valid_until`.
- `include_in_chatbot`.
- optimistic version وtimestamps.

Constraint يمنع `from|fixed` بلا سعر موثوق، ويمنع القيمة السالبة. الحسابات
والتحويلات تستخدم `Decimal/Numeric` فقط.

### 7.3 `hub_catalog_translations`

- `item_id`, `locale`؛ unique معًا.
- `name`, `short_description`, `description`.
- `features` كمصفوفة مهيكلة ومحدودة عبر schema، لا HTML عشوائي.
- `price_label_override` غير مسموح له بإخفاء/تغيير قيمة السعر الرقمية.
- `seo_title`, `seo_description`, `image_alt`.

اللغات المسموحة: `ar|en|ru|it`.

### 7.4 `hub_site_sections` وtranslations

- `page_key` و`section_key` معروفان مسبقًا من registry.
- `section_type` من قائمة محددة: hero, text, feature_grid, gallery, CTA.
- ترتيب وحالة وmedia references.
- payload محدود ومتحقق حسب `schema_version`.
- لا JavaScript ولا iframe ولا raw HTML.

### 7.5 `hub_media_assets` و`hub_media_variants`

- UUID/public id، content hash، MIME الحقيقي، الحجم والأبعاد.
- original filename للعرض فقط، وليس مسار تخزين.
- حالة scan/processing/ready/quarantined/archived.
- variant paths وأبعادها.
- uploader، branch، timestamps، reference count.
- translations للـalt/caption عند الحاجة.

### 7.6 `hub_content_revisions`

- append-only snapshot لكل تغيير محفوظ.
- entity type/id/version.
- actor، reason، timestamp، previous hash، payload hash.
- لا حذف أو تعديل عبر workflows العادية.

### 7.7 `hub_publications`

- `id`, `branch_id`, monotonic `version`.
- immutable `snapshot_json` و`content_hash`.
- validation report summary.
- publisher، reason، timestamp.
- `rolled_back_from_id` عند الرجوع.

صف `HubSiteState` أو مكافئه يحمل `current_publication_id`، ويُقفل row-level
أثناء publish/rollback لمنع سباق إصدارين.

### 7.8 `hub_preview_tokens`

- لا يخزن token الخام؛ يخزن hash فقط.
- مرتبط بالمستخدم والفرع وrevision المراد معاينته.
- صلاحية قصيرة، استعمال محدود، `Cache-Control: no-store`.
- Preview pages تحمل `noindex,nofollow`.

### 7.9 إعداد الشات

`hub_chat_configs` typed:

- `enabled`.
- handoff/fallback mode من enum.
- non-secret behavior limits المسموحة.
- translations لرسالة الترحيب والنص البديل.

يُضاف locale أو translation model إلى `ChatPublicFact`، مع الحفاظ على حالات
الاعتماد والمصدر والانتهاء. cache key للـprompt يصبح branch + locale +
publication version.

---

## 8. عقود الـAPI المقترحة

### 8.1 Staff authoring APIs

كلها تحت `/api/v1/hub`، Auth إلزامي، وbranch موثوق من عضوية المستخدم:

- `GET/PUT /hub/site-profile`
- `GET/POST/PATCH /hub/catalog/items`
- `GET/POST/PATCH /hub/site-sections`
- `POST /hub/media`
- `GET /hub/media`
- `POST /hub/preview-tokens`
- `POST /hub/publications/validate`
- `POST /hub/publications/publish`
- `POST /hub/publications/{id}/rollback`
- `GET /hub/publications`
- `GET/PUT /hub/chat-config`
- CRUD إداري مراجع لـ`ChatPublicFact`.

المسارات الفعلية تُثبت في task brief بعد فحص تضارب router ordering والعقود
القائمة. Public routes لا تشارك schemas التي تحتوي draft/audit fields.

### 8.2 Public read APIs

- `GET /api/v1/public/site/bootstrap?locale=ar`
- `GET /api/v1/public/site/catalog/{type}?locale=ar`
- `GET /api/v1/public/site/pages/{page}?locale=ar`
- `GET /api/v1/public/site/sitemap.xml`
- `/media/{content_hash}/{variant}` عبر مسار same-origin ثابت.

قواعد العقود العامة:

- الفرع يُحل من hostname كما يحدث في chat/contact؛ لا يقبل `branch_id`.
- يعيد published snapshot فقط.
- ETag من content hash، ويدعم `If-None-Match -> 304`.
- Cache-Control مراجع مع `stale-while-revalidate` للمحتوى العام.
- لا PII ولا IDs تشغيلية داخلية ولا تكاليف ولا مصدر مورد.
- price fields محذوفة عندما تمنعها البوابة، لا تُرسل كقيمة مخفية للعميل.
- العقود strict و`extra=forbid` في الكتابة.

---

## 9. واجهة مركز الإدارة

يُعاد تنظيم `HubManagementView` تدريجيًا، مع الحفاظ على الحجوزات ونماذج
التواصل الموجودة، إلى الأقسام التالية:

1. **نظرة عامة:** الإصدار المنشور، المسودات، أخطاء التحقق، آخر نشر.
2. **محتوى الموقع:** الصفحات والأقسام والـHero وCTA.
3. **الخدمات والأسعار:** الكتالوج والفلاتر والمصادر وحالة السعر.
4. **الوسائط:** رفع وبحث ومعاينة واستخدامات الصورة.
5. **SEO والتواصل:** Profile وmetadata والسوشيال والمواعيد.
6. **الشات بوت:** التشغيل والترحيب والحقائق والاختبار والتحليلات الآمنة.
7. **النشر:** Validate، Preview، Diff، Publish، History، Rollback.
8. **الحجوزات والرسائل:** workflows الحالية بعد تصحيح عقودها إن لزم.

### UX إلزامي

- الواجهة عربية/إنجليزية RTL/LTR.
- محرر المحتوى يعرض تبويبات AR/EN/RU/IT مع نسبة اكتمال.
- Auto-save غير مطلوب في V1؛ الحفظ explicit لمنع تغييرات غير مقصودة.
- Unsaved changes warning.
- Loading/empty/error/retry states.
- Diff واضح قبل النشر: أضيف/تغير/أخفي/سعر تغير.
- Preview للهاتف والكمبيوتر ولكل لغة.
- السعر يعرض مصدره ووقت آخر مزامنة.
- لا Branch Switcher.
- أزرار النشر والرجوع لا تعتمد على الإخفاء البصري؛ API يحميها.
- Keyboard focus وARIA labels وcontrast وفق design system.

---

## 10. صلاحيات وأمان

### 10.1 صلاحيات مقترحة

- `website.content.view`
- `website.content.edit`
- `website.media.manage`
- `website.chatbot.manage`
- `website.publication.preview`
- `website.publication.publish`
- `website.price.publish`
- `website.publication.rollback`

إذا لم يكن permission catalog مهيأ لهذه الدقة في المرحلة الأولى:

- manager: view/edit/upload/preview فقط.
- super_admin: publish/rollback/price publish.

ثم تنتقل mapping إلى permissions الصريحة قبل منح صلاحيات لموظفين إضافيين.

### 10.2 إجراءات حساسة

تحتاج Step-Up purpose-bound + reason:

- Publish.
- Rollback.
- تفعيل أسعار رقمية.
- تشغيل/إيقاف Chatbot عالميًا.
- تغيير exact location أو بيانات قانونية عامة.
- Archive لمحتوى منشور أو صورة مستخدمة.

### 10.3 حماية المحتوى

- Plain text أو Markdown allowlist sanitized؛ لا raw HTML في V1.
- منع script/event handlers/unsafe URLs.
- روابط خارجية HTTPS فقط مع قواعد scheme/domain مناسبة.
- ملفات الصور تفحص بالـmagic bytes ثم decode/re-encode.
- strip EXIF، ورفض SVG/GIF في V1.
- حد للحجم والأبعاد وعدد الملفات والـrate limit.
- content-addressed names، ومنع path traversal.
- media upload لا يكتب داخل Git checkout أو frontend `public/`.
- كل mutation يكتب Audit بلا أسرار أو payload ضخم.

---

## 11. مكتبة الوسائط والبنية التشغيلية

### 11.1 التخزين

يُنشأ تخزين دائم مثل:

- host path مراجع: `/var/lib/resort-os/public-media`، أو named volume واضح.
- mount للـBackend على نفس المسار.
- `/media/` proxy من Marketing Nginx إلى مسار القراءة العام.
- أسماء الملفات مبنية على SHA-256، لذلك يمكن استخدام immutable cache.

لا يُستخدم `backend/uploads` الحالي كمصدر وحيد قبل إضافة volume وbackup؛
المسار الحالي داخل container غير كافٍ لضمان البقاء بعد rebuild.

### 11.2 المعالجة

- Original محفوظ بعد validation، مع نسخة معالجة خالية من metadata.
- variants مبدئية: thumbnail، card، hero.
- WebP إلزامي؛ AVIF اختياري بعد قياس الأداء والتوافق.
- focal point بدل crop ثابت لكل صفحة.
- jobs الثقيلة عبر Celery إذا تجاوزت المعالجة حد الطلب القصير.
- asset لا يصبح `ready` قبل نجاح كل variant مطلوب.

### 11.3 النسخ الاحتياطي

- إضافة media volume إلى backup service.
- manifest يومي: path/hash/size/database asset id.
- restore drill معزول قبل Go-Live.
- DB restore وحده لا يكفي؛ media archive والداتابيز يجب أن يتوافقا.

---

## 12. دمج الشات بوت

### 12.1 مصدر المعرفة

- المحتوى المنشور الموسوم `include_in_chatbot=true` يتحول أثناء publication
  إلى facts مرتبطة بإصدار المصدر.
- FAQ اليدوي يبقى داخل `ChatPublicFact` مع Draft/Approved/Retired.
- النشر بواسطة super_admin هو لحظة الاعتماد؛ المسودة لا تدخل الـprompt.
- rollback يعيد facts المطابقة للإصدار المرجوع إليه وير retire النسخة
  المشتقة الجديدة دون حذف التاريخ.

### 12.2 اللغات

- `build_system_prompt` يصبح locale-aware.
- لا يحمّل حقائق اللغات الأربع في prompt واحد.
- publication يمنع fact بلا ترجمة مطلوبة.
- cache key يشمل branch/locale/publication version.

### 12.3 التشغيل والإيقاف

التشغيل يحتاج بوابتين معًا:

1. `hub_chat_config.enabled=true` في الإصدار المنشور.
2. Provider/config/budget guard جاهز في Backend.

عند الإيقاف:

- الموقع لا يعرض Widget.
- بدء جلسة أو إرسال رسالة يفشل برسالة عامة و`no-store`.
- لا يتغير مفتاح Gemini ولا يُكشف سبب داخلي للضيف.

### 12.4 التحليلات والخصوصية

المسموح في V1:

- عدد الجلسات والرسائل.
- التقييم المتوسط والتوزيع.
- tokens والتكلفة المقدرة والرفض حسب السبب.
- availability/circuit state إجماليًا.

غير المسموح:

- عرض أو تخزين رسائل الضيف أو ردود النموذج الخام.
- اسم/هاتف/بريد داخل prompt.
- ادعاء «أكثر الأسئلة غير المجابة» من دون قرار خصوصية وموديل تجميع منفصل.

---

## 13. Public Truth والأسعار

قاعدة الفعالية:

```text
effective_publication = static_truth_gate AND approved_server_publication
```

- `PUBLIC_TRUTH` يبقى emergency upper bound داخل Marketing build.
- Backend publication policy لا يستطيع تجاوز gate مغلق.
- في أول Release، `prices=false` كما هو.
- UI يسمح بإعداد سعر كمسودة، ويعرض أن النشر الرقمي محظور.
- Public snapshot يحول العنصر إلى `contact_for_price` أو يحذف السعر.
- Approval B يحدد الفئات، ثم يحدث gate في diff مستقل مع تحديث
  `check-public-truth.mjs` وقرار مؤرخ واختبارات.
- أي price publish يسجل old/new/source/effective dates/actor/reason.
- لا تُستنتج عروض أو خصومات من فرق سعرين من دون قرار promotions منفصل.

---

## 14. خطة الهجرة والتوافق

### 14.1 قواعد عامة

- migrations forward-only/additive في أول إصدار.
- لا تعديل migration مطبقة.
- Alembic يبقى single head.
- لا حذف لجداول Hub أو حقول موجودة في نفس الحزمة.
- لا تغيير لعقود contact/chat/dining العامة القائمة إلا بإصدار متوافق.

### 14.2 استيراد المحتوى الحالي

1. أخذ manifest من Marketing commit `16f8f2c` للنصوص والصور والعناصر.
2. mapper صريح للصفحات والعناصر المعروفة، لا parsing عشوائي لملفات Vue.
3. importer idempotent، dry-run افتراضي، وموسوم
   `source=current-static-16f8f2c`.
4. إنشاء العناصر كـDraft فقط.
5. لا أسعار رقمية ولا claims جديدة أثناء الاستيراد.
6. مراجعة الصور والترجمات الأربع والـAlt Text في Preview.
7. نشر snapshot يطابق المحتوى الحالي الآمن قبل إزالة أي fallback.

لا يستورد المشروع القديم إلى الإنتاج. إذا وُجد أصل مفيد فيه، يُراجع ملفًا
بملف ويُرفع كـDraft جديد مع source reference.

### 14.3 وضع Marketing الهجين

1. إضافة typed Public Site client/store.
2. تحميل bootstrap مرة واحدة لكل locale/version.
3. الصفحات تنتقل واحدة واحدة من المصفوفات الثابتة إلى selectors مهيكلة.
4. الاحتفاظ بالقيم الثابتة الآمنة كfallback مؤقت.
5. parity screenshots وtruth check لكل صفحة.
6. بعد ثبات الإصدار، حذف `/settings/public` ghost path وhard-coded content
   الذي أصبح له مصدر DB، مع إبقاء i18n الخاص بواجهة المستخدم.

### 14.4 توافق SEO

- title/description/OG tags تقرأ من snapshot.
- sitemap العام يتولد من المنشور فقط.
- Preview يحمل noindex.
- `structuredBusinessData` يبقى مغلقًا حتى اعتماد منفصل.
- أي prerender/SSR تحسين لاحق، وليس شرطًا لتأسيس CMS V1 ما لم يثبت اختبار
  crawler أن metadata الديناميكية غير كافية.

---

## 15. حزم التنفيذ المرحلية

لا تبدأ أي حزمة قبل Approval A، ولا تُنفذ الحزم كـoverhaul واحد.

### MKT-CMS-01A — Discovery freeze والعقود

**الهدف:** تحويل هذه الخطة إلى task brief مبني على أحدث commits.

المهام:

- حفظ status/diff للـworktrees الحالية وعدم امتصاص تغييرات POS غير المرتبطة.
- فحص models/schemas/crud/services/router/tests/migrations النهائي.
- تثبيت registry للصفحات والأنواع واللغات وسياسات السعر.
- تثبيت API schemas وpermission matrix.
- ADR قصير لاختيار publication snapshot وmedia storage.
- threat model للـpreview/upload/public API.

**Definition of Done:** task brief approved، لا كود إنتاجي، ولا business
assumption غير مصرح به.

### MKT-CMS-01B — Backend authoring foundation

**الهدف:** الجداول والخدمات والصلاحيات دون Public consumption.

المهام:

- migrations additive.
- models/schemas/crud/services حسب layering.
- optimistic concurrency وrevision append.
- validation engine للغات والسعر والبوابات والوسائط.
- staff CRUD مع branch fail-closed.
- Audit وStep-Up وreason للعمليات الحساسة.
- targeted backend tests وPostgreSQL constraints/concurrency tests.

**DoD:** لا endpoint عام يعرض Draft؛ migration cycle واختبارات الصلاحيات
والسباق ناجحة.

### MKT-CMS-01C — Media pipeline

**الهدف:** رفع وصيانة الصور بصورة دائمة وآمنة.

المهام:

- persistent volume وCompose wiring.
- validation/decode/re-encode/EXIF stripping/variants.
- staff media API وUI.
- public same-origin media delivery وcache headers.
- reference protection وarchive.
- backup manifest وrestore drill محلي.

**DoD:** rebuild لحاوية Backend لا يفقد الصور، والملف المخالف يُرفض،
والصورة المستخدمة لا تُحذف.

### MKT-CMS-01D — Staff Control Center

**الهدف:** تحرير ومراجعة المحتوى من تطبيق الموظفين.

المهام:

- تقسيم Hub view إلى مكونات محدودة المسؤولية.
- محتوى/كتالوج/وسائط/SEO/Chat/Publishing tabs.
- AR/EN staff UI وAR/EN/RU/IT content editors.
- preview token workflow.
- diff وvalidation report.
- loading/error/empty/accessibility tests.

**DoD:** manager يحفظ Draft ولا ينشر، super_admin فقط يرى وينفذ Publish
بعد Step-Up.

### MKT-CMS-01E — Publication وPublic API

**الهدف:** Snapshot ذري قابل للـrollback.

المهام:

- validate/publish/rollback transaction.
- row lock/idempotency/version/hash.
- public host-to-branch resolution.
- bootstrap/catalog/page/sitemap APIs.
- Redis cache invalidation وETag/304.
- suppression كامل للحقول المحظورة.

**DoD:** concurrent publish لا ينشئ current versions متضاربة، وrollback
يعيد الإصدار السابق دون DB restore.

### MKT-CMS-01F — Marketing integration

**الهدف:** استهلاك المحتوى المنشور بلا downtime.

الترتيب المقترح للصفحات:

1. Activities.
2. Events.
3. Packages.
4. Timeshare.
5. FAQ وContact.
6. Home sections.
7. Beach/Rooms/Restaurant highlights.

المهام:

- typed store/client/fallback.
- page adapters ثم إزالة المصفوفات المستبدلة.
- إصلاح دعم overrides/locale للأربع لغات.
- runtime chatbot visibility من bootstrap.
- SEO/sitemap consumption.
- truth/type-check/build/page tests.

**DoD:** كل صفحة مطابقة للمحتوى المعتمد، لا flashes للأسعار أو draft،
والتعطل يعيد fallback آمنًا.

### MKT-CMS-01G — Chatbot integration

**الهدف:** مصدر معرفة واحد وتشغيل runtime آمن.

المهام:

- locale-aware facts/prompt cache.
- publication-derived facts.
- typed Chat config وdual enable gate.
- admin knowledge editor/simulator.
- privacy-safe analytics.
- prompt injection/content leakage regressions.

**DoD:** Draft لا يجيب عنه الشات، والـrollback يغير الحقائق للإصدار الصحيح،
ولا تخزن رسائل خام.

### MKT-CMS-01H — Migration/UAT/release candidate

**الهدف:** ملء المسودات الحالية وإثبات الجاهزية دون إنتاج.

المهام:

- importer dry-run ثم local/staging apply.
- owner content preview.
- أربع لغات وهاتف/كمبيوتر/RTL/LTR.
- price gate false proof.
- security/accessibility/performance/UAT.
- release manifests/digests/rollback plan.

**DoD:** تقرير قبول جاهز لطلب Approval C، ولا يوجد نشر إنتاجي.

### MKT-CMS-01I — Production rollout

**ممنوعة قبل Approval C.**

الترتيب:

1. backup DB + media + image manifests.
2. نشر Backend additive migration/API مع الميزة غير مفعلة للعامة.
3. health وmigration/API staff checks.
4. نشر Marketing hybrid build.
5. health/domain/truth/SEO/fallback checks.
6. نشر أول snapshot آمن بلا أسعار رقمية.
7. Chat E2E بأربع لغات ضمن budget.
8. burn-in ومراجعة logs/cache/backup.
9. handoff وتحديث حالة المشروع.

---

## 16. معايير القبول

### المحتوى والنشر

1. Given عنصر Draft، when يطلبه زائر، then لا يظهر في أي public API.
2. Given ترجمة ناقصة، when يحاول ناشر Publish، then يرفض بتقرير الحقول.
3. Given مدير، when يحاول Publish مباشرة، then 403 حتى لو أظهر الزر يدويًا.
4. Given super_admin بلا Step-Up أو reason، then يرفض Publish/Rollback.
5. Given طلبا Publish متزامنان، then يوجد current publication واحد فقط.
6. Given rollback، then تعود النصوص والصور والسياسات والحقائق كإصدار واحد.
7. Given ETag مطابق، then public API يعيد 304 بلا payload.
8. Given API unavailable، then الموقع يعرض fallback آمنًا بلا سعر رقمي.

### الأسعار

9. Given `PUBLIC_TRUTH.publish.prices=false`، then لا يوجد رقم سعر في
   snapshot أو DOM أو schema أو chatbot prompt.
10. Given سعر مرتبط بـDining/Beach/PMS، then Backend يتحقق من المصدر ولا
    يقبل client-supplied trusted price.
11. Given تغير سعر المصدر بعد النشر، then يظهر drift للإدارة ولا يتغير
    public snapshot حتى إعادة نشر معتمدة.
12. Given سعر manual، then يُخزن Numeric/Decimal وتُسجل old/new/source.

### اللغات والواجهة

13. المحتوى المنشور متاح AR/EN/RU/IT من نفس publication version.
14. واجهة الموظفين سليمة RTL/LTR وتعمل بلوحة المفاتيح وعلى الهاتف.
15. الروسية والإيطالية لا تسقطان بصمت إلى override إنجليزي.
16. Preview لا يُفهرس ولا يُخزن في cache عام.

### الوسائط

17. declared MIME مخالف للـbytes يُرفض.
18. ملف كبير/أبعاد خطرة/SVG/GIF يُرفض في V1.
19. EXIF يزال والvariants تُنتج قبل `ready`.
20. asset referenced لا يُحذف، وarchive لا يكسر snapshot قديمًا.
21. container rebuild وmedia restore drill يحافظان على الملفات والhashes.

### الشات والخصوصية

22. الشات يستخدم approved non-expired facts للغة المطلوبة فقط.
23. Draft/retired/expired facts لا تدخل الـprompt.
24. Runtime disable يخفي Widget ويمنع جلسة جديدة بصورة fail-closed.
25. API key/system prompt/security limits غير قابلة للقراءة أو التعديل من UI.
26. قاعدة البيانات لا تحتوي message/reply raw text بعد E2E.
27. حقائق السعر والموقع والوعود المحظورة لا تظهر في الرد.

### العزل والتدقيق

28. لا Branch Switcher، لكن user خارج العضوية لا يقرأ أو يعدل المحتوى.
29. public hostname غير معروف لا يحصل على branch افتراضي.
30. audit يحتوي actor/action/target/reason/version/request context دون سر.

---

## 17. خطة الاختبارات

### Backend targeted

- Hub CRUD/validation/publication/rollback.
- Permissions/branch/step-up/audit.
- Numeric price constraints/source resolution.
- Preview token expiry/hash/reuse/no-store.
- Media security/reference/processing.
- Public host resolution/cache/ETag/truth suppression.
- Chat facts locale/status/expiry/publication rollback.
- PostgreSQL concurrency: publish/version/current pointer/media reference.

### Frontend staff

- route/permission guards.
- draft editor validation وdirty state.
- locale completion and RTL/LTR.
- publish modal/Step-Up/diff.
- media upload error states.
- accessibility keyboard/focus.

### Marketing

- bootstrap success/failure/cache/locale switch.
- safe fallback لكل صفحة.
- no draft/no price/no disallowed claims.
- runtime chatbot visibility.
- SEO metadata وsitemap.
- `node scripts/check-public-truth.mjs`.
- `npm run validate`.

### Full gates قبل Release Candidate

```bash
# Resort OS
bash scripts/agent-check.sh
git diff --check
cd backend
.venv/bin/pytest tests/ -v
.venv/bin/alembic heads
cd ../frontend
pnpm run type-check:all
pnpm --filter el-kheima test:frontend
pnpm run build:all

# Marketing website
cd /home/wego/projects/elkheima-marketing-website
npm run validate
npm run audit:prod
```

تُراجع أوامر Compose الفعلية مع env آمن قبل النشر. لا يُدّعى نجاح أي gate
من رقم قديم؛ تُحفظ نتائج التشغيل الفعلية في handoff.

---

## 18. الملفات المتوقعة

هذه قائمة تقديرية تُثبت بعد MKT-CMS-01A:

### Resort OS Backend

- `backend/app/modules/hub/models.py`
- `backend/app/modules/hub/schemas.py`
- `backend/app/modules/hub/crud.py`
- `backend/app/modules/hub/services.py`
- `backend/app/modules/hub/api/router.py`
- `backend/app/modules/chat/models.py`
- `backend/app/modules/chat/crud.py`
- `backend/app/modules/chat/services.py`
- `backend/app/modules/chat/api/router.py`
- core permission catalog/audit utilities عند الحاجة المراجعة فقط.
- forward Alembic migrations.
- Hub/Chat/API/security/concurrency tests.

### Staff frontend

- `frontend/apps/el-kheima/src/views/admin/HubManagementView.vue`
- مكونات مركزة تحت `components/hub/` عند ثبوت الحاجة.
- `frontend/packages/core/src/api/endpoints.ts`
- types/stores/i18n AR/EN.
- frontend tests.

### Production wiring

- `docker-compose.prod.yml` لإضافة media volume.
- Backend/Marketing Nginx `/media/` proxy/cache.
- backup/health scripts وإثبات restore.

### Marketing repository

- `src/api/publicSite.ts` أو الاسم النهائي المراجع.
- typed public content store/types.
- `src/App.vue` لتفعيل runtime Chatbot gate.
- صفحات `src/apps/public/*` بالتتابع.
- SEO/public truth checks.
- `nginx.spa.conf` لمسار media إذا اعتمد التصميم.
- tests/documentation.

لا يُلمس أي ملف POS محلي متغير حاليًا ضمن هذه المهمة.

---

## 19. خطة النشر والتراجع

### قبل النشر

- تثبيت exact source commits للمستودعين.
- worktrees نظيفة ومراجعة diffs.
- DB backup جديد والتحقق من الحجم/hash.
- media backup/manifest.
- حفظ image IDs/tags وcurrent symlinks.
- `alembic heads` واحد وmigration dry run.
- Marketing build canary.
- نشر snapshot آمن في staging/preview أولًا.

### نشر متدرج

- Backend/migration additive أولًا، feature غير مفعلة.
- Staff control center ثانيًا.
- Marketing hybrid ثالثًا، يستمر على fallback إن لم توجد publication.
- أول publication أخيرًا.
- أقل مجموعة services تتغير؛ لا إعادة إنشاء DB/Redis.

### التراجع

- خطأ محتوى: rollback publication فقط.
- خطأ Marketing: إعادة image/release السابق `16f8f2c` أو الـrelease الموثق
  وقت التنفيذ؛ Backend additive يبقى.
- خطأ Backend: إعادة image السابق المتوافق؛ لا DB restore لمجرد rollback
  تطبيقي.
- خطأ media: إيقاف النشر الجديد واستعادة asset/manifest المحدد، لا استبدال
  volume كامل دون reconciliation.
- migration downgrade في الإنتاج غير افتراضي؛ schema additive تبقى إن كان
  التطبيق السابق يتجاهلها.
- لا DNS rollback لأن DNS خارج نطاق الحزمة.

بعد التراجع تُعاد health/domain/API/cache/chat/truth checks ويُكتب Audit
وحادثة/handoff.

---

## 20. المراقبة والتشغيل

- metric لنجاح/فشل public bootstrap ووقت الاستجابة.
- current publication version/hash في health diagnostic داخلي.
- cache hit/miss وinvalidation failures.
- media processing queue failures والمساحة الحرة.
- publish/rollback failure counters.
- Chat provider availability/budget/rejections دون نص المحادثة.
- تنبيه عند انتهاء fact أو offer قريبًا.
- فحص دوري للروابط والصور المفقودة والترجمات الناقصة.
- backup يشمل DB + media، وhealth timer يتحقق من آخر نجاح.

لا تُرسل أسرار أو محتوى Draft أو PII إلى logs/metrics/alerts.

---

## 21. المخاطر والتخفيف

| الخطر | التخفيف |
|---|---|
| تحول CMS إلى key/value فوضوي | جداول typed + registries + strict schemas |
| سعر عام مختلف عن التشغيل | source link + publish-time snapshot + drift warning |
| تجاوز Public Truth | static upper gate + server validation + owner approval |
| فقد صور بعد Docker rebuild | persistent volume + backup + restore drill |
| ظهور نصف تحديث | immutable atomic publication snapshot |
| حذف صورة مستخدمة | references + archive + no hard delete |
| تسريب Draft أو فرع | host-derived branch + separate public schemas |
| XSS من المحتوى | no raw HTML + sanitizer + CSP |
| Prompt injection/معلومة مختلقة | approved facts only + current system rules |
| تضخم prompt | locale/version filtering + limits + cache |
| كسر SEO | dynamic metadata + generated sitemap + crawler test |
| كسر الموقع عند API outage | safe static fallback + stale published cache |
| تضارب مع تغييرات POS الحالية | dedicated owning worktree + path-scoped staging |
| توسع غير منضبط | حزم صغيرة، DoD لكل حزمة، لا overhaul |

---

## 22. شروط التوقف الإلزامي

يتوقف Codex ويطلب قرار Mohamed إذا ظهر أي من الآتي:

- الحاجة إلى نشر سعر/عرض/موقع/وعد غير معتمد.
- تعارض بين سعر التشغيل والسعر الذي تريد الإدارة نشره.
- قرار قانوني أو تعاقدي يخص Timeshare/Blue Bay.
- حذف أو تحويل بيانات موجودة بطريقة غير قابلة للرجوع.
- الحاجة إلى سر أو صلاحية خارج النطاق.
- migration destructive أو تضارب Alembic heads.
- فشل متكرر في restore أو concurrency أو security gate.
- تداخل لا يمكن عزله مع تغييرات المستخدم المحلية.
- الحاجة لتغيير DNS/TLS أو provider billing.
- تقرير UAT يحمل finding عاليًا أو ماليًا غير مغلق.

لا يمنح ضغط الوقت إذنًا بتجاوز أي Stop condition.

---

## 23. تحديثات التوثيق المطلوبة بعد الاعتماد

بعد Approval A فقط:

1. إضافة MKT-CMS-01A إلى لوحة التنفيذ كمهمة جارية واحدة.
2. تحديث `wagdy.md` بقرار المالك والنطاق المعتمد.
3. تحديث الخطة النهائية بحزمة جديدة وحالة Gate 4/Chat.
4. إنشاء task brief لكل حزمة، لا Brief واحد ضخم.

بعد كل حزمة:

- تحديث الأدلة والنتائج، لا نسخ checkpoint كامل.
- handoff يذكر commits/checks/migrations/production effect/rollback.
- لا commit/push/deploy إلا بما تسمح به موافقة المرحلة.

بعد Approval C والنشر:

- تحديث `PROJECT_STATUS.md` بالإصدار الفعلي والـdigests والـhealth evidence.
- تحديث `wagdy.md` ولوحة التنفيذ والخطة النهائية.
- handoff للإصدار ونقطة التراجع والمخاطر المتبقية.

---

## 24. سجل الحالة

| الحزمة | الحالة الحالية | الموافقة المطلوبة |
|---|---|---|
| MKT-CMS-01A — discovery/contracts | NOT STARTED | Approval A |
| MKT-CMS-01B — backend foundation | NOT STARTED | Approval A + accepted brief |
| MKT-CMS-01C — media | NOT STARTED | Approval A + accepted brief |
| MKT-CMS-01D — staff UI | NOT STARTED | Approval A + accepted brief |
| MKT-CMS-01E — publication/public API | NOT STARTED | Approval A + accepted brief |
| MKT-CMS-01F — Marketing integration | NOT STARTED | Approval A + accepted brief |
| MKT-CMS-01G — Chat integration | NOT STARTED | Approval A + accepted brief |
| MKT-CMS-01H — migration/UAT/RC | NOT STARTED | Approval A + owner review |
| Numeric public prices | PROHIBITED | Approval B |
| MKT-CMS-01I — production | PROHIBITED | Approval C |

**الحالة النهائية لهذه الوثيقة حتى رد Mohamed:**

```text
PLAN READY
IMPLEMENTATION STOPPED
OWNER APPROVAL REQUIRED
NO CODE / DATA / VPS AUTHORIZATION GRANTED
```

