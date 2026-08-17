# REL-17b — لايت مود + نص أوضح لتطبيق المالك

**التاريخ:** 2026-08-17
**المنفّذ:** Claude (نفس الجلسة، متابعة لـREL-17)
**الفرع:** `codex/rel-15-auth-ops-readiness`
**Implementation/Release commit:** `65a06052dbbad5ed0c2c2737f80b640da159cac2`

## 1. الدافع

Mohamed جرّب تطبيق المالك (owner.elkheima.com) بنفسه، ولاحظ إن الأرقام والنص
صغيرة وهو لابس نظارة قراءة، وطلب نظام لايت مود كامل — قرار منتج صريح من
المالك نفسه، بيلغي قرار "dark-first، لا light mode" الأصلي في Decision 0004
(اللي كان قرار تصميم افتراضي وقت البناء، مش قيد نهائي).

## 2. التنفيذ

- **لايت مود حقيقي**: استخدم نفس الآلية الموجودة بالفعل ومُختبرة في
  `el-kheima` (`@resort-os/core`'s `useTheme()`/`initTheme()` +
  `@resort-os/ui`'s `<ThemeToggle>`) بدل اختراع نظام جديد. `tailwind.config.js`
  بتاع تطبيق المالك بقى الألوان `owner-*` بتتحل من CSS custom properties
  (قيم فاتحة على `:root`، قيم داكنة — نفس القيم الأصلية بالظبط، من غير أي
  تغيير — تحت `.dark`)، فكل استخدام موجود لـ`owner-*` classes عبر الـ17 شاشة
  (~450 استخدام) بيتلوّن صح تلقائيًا من غير أي تغيير في مكان الاستخدام نفسه.
  اختار درجة 700 (أغمق) للأخضر/الأحمر/الكهرماني في اللايت مود تحديدًا لأن
  الألوان دي بتُستخدم كنص صغير كمان مش بس تعبئة/badges — اتحقق من التباين
  فعليًا مقابل WCAG AA (4.5:1).
- حوّل ~12 استخدام لـTailwind classes غامقة ثابتة (`bg-red-950/40` إلخ،
  مستخدمة في صناديق خطأ/تحذير) عبر 4 شاشات لمكافئها المعتمد على الـtoken
  الجديد (`owner-red/10` إلخ) — كانت هتظهر باهتة/غير واضحة في اللايت مود.
  باج تباين حقيقي اتصلح أثناء المراجعة: badge عداد الاستثناءات الحرجة كان
  نص أسود على أحمر — بيفشل WCAG AA مع الأحمر الفاتح الجديد — اتحوّل لنص
  أبيض.
- **تفضيل حجم نص (عادي/كبير/أكبر)**: composable جديد `useTextScale.ts`
  بيغيّر `font-size` على `<html>` (17/19/21px) بدل تعديل ~200 استخدام
  Tailwind text-size فردي منتشر في كل شاشة — كل حجم نص rem-based في
  Tailwind وclamp() الخاص بـ`.metric-value` بيكبروا مع بعض من إعداد واحد،
  فبيحل شكوى "الأرقام والنص صغيرة" بشكل شامل وقابل للعكس.
- زرار "Aa" جديد + `<ThemeToggle>` في هيدر `AppShell.vue`.
- **باج حقيقي اتصلح اكتشفه e2e test موجود بالفعل**: ارتفاع `.bottom-nav`
  الأدنى الثابت (56px) وpadding المحجوز في `.owner-main` (56px برضو) طلعوا
  مش متزامنين لما جذر حجم الخط كبر (محتوى النافبار بقى ارتفاعه الفعلي
  ~57.3px) — يعني بكسر واحد من محتوى الشاشة كان بيغطّيه النافبار في شاشات
  ضيقة. اتصلح بتحويل الاتنين لنفس قيمة rem (`3.5rem`) عشان يفضلوا متزامنين
  عند أي حجم نص.

## 3. البوابات

```
frontend  pnpm --filter owner run type-check   → نظيف
frontend  pnpm --filter owner run build         → نظيف
frontend  pnpm --filter owner run test:e2e      → 12/12 (320/390/768/1024/1280px)
frontend  pnpm run type-check:all               → نظيف (el-kheima + owner)
frontend  VITE_PUBLIC_SITE_URL=... build:all    → نظيف
```

**تحقق تفاعلي حي حقيقي** (مش افتراض) عبر Playwright حي — سيرفر dev محلي،
ضغط فعلي على زرار الـتبديل وزرار "Aa":
- ضغطة تبديل الوضع: `.dark` class + `color-scheme` اتقلبوا صح، خلفية
  `.owner-card` الفعلية اتغيّرت من `rgb(255,255,255)` (أبيض، لايت) لـ
  `rgb(28,27,26)` (نفس `#1C1B1A` الأصلي بالظبط، دارك) — القيمة الأصلية
  محفوظة حرفيًا.
- ضغطات "Aa": `17px → 19px → 21px → 17px` بالترتيب الصحيح، مع حفظ
  الاختيار في `localStorage` تحت `owner-text-scale`.
- صفر overflow أفقي في أي لحظة من التبديلات.

## 4. سجل النشر على VPS

**Release commit:** `65a06052dbbad5ed0c2c2737f80b640da159cac2`
**Release directory:** `/opt/resort-os-releases/65a06052dbbad5ed0c2c2737f80b640da159cac2`
**النطاق**: تغيير frontend بحت — مفيش migration، مفيش تعديل backend. الحاوية
الوحيدة اللي اتبنت واتستبدلت هي `owner` — باقي الحاويات (backend/celery/
el_kheima/nginx) فضلت شغالة زي ما هي من غير أي لمس، لأنها مش متأثرة بالكومنت ده.

- الأرشيف اتنسخ وتحقق منه بـSHA-256 مطابق (local ↔ remote):
  `bf852d5a84953afd5d4ef22a9aff6feebb6605cbba339a1c26e70b90be3e0d27`
- `.env.prod` اتنسخ من الإصدار النشط الحالي بصلاحية `0600` بدون عرضه،
  `validate_prod_env.py` → PASS.
- Rollback: `resort-os-rollback/owner:pre-65a0605...` (الصورة اللي كانت
  شغالة قبل الديبلوي ده) موسومة ومسجّلة في
  `/var/backups/resort-os/source-releases/65a0605...-rollback-images.txt`.
- Build: `docker compose build owner` → نجح.
- Replace: `up -d --no-deps owner` → healthy فورًا، `RestartCount=0`.
- تحقق مباشر: الـbundle المنشور فعليًا (`AppShell-D0IZ9X2O.js`,
  `index-BPCj3WxY.js`) بنفس الـhash بالظبط اللي طلع من الـbuild المحلي —
  تأكيد إن الكود المنشور هو نفسه المُختبر بالظبط.
- `curl -fsSI https://owner.elkheima.com/` → `HTTP/2 200`.
- صفر خطأ جديد (`[emerg]`/`[crit]`/`[alert]`) في لوجات nginx/owner.
- `/opt/resort-os-current` اتحدّث ليشير للإصدار الجديد.
- Health gate الرسمي: `RESORT_HEALTHCHECK_OK passes=16`.

### الرجوع (Rollback)

```
docker tag resort-os-rollback/owner:pre-65a0605... resort-os-prod-owner:latest
docker compose ... up -d --no-deps owner
```
مفيش قاعدة بيانات لاسترجاعها — التغيير ده frontend بحت.

## 5. الخلاصة

لايت مود كامل + تفضيل حجم نص (عادي/كبير/أكبر) اتضافوا لتطبيق المالك،
بإعادة استخدام كاملة للآلية الموجودة أصلاً (`useTheme`/`ThemeToggle`)،
اتحقق منهم فعليًا بتفاعل حي (مش مجرد build ناجح)، ونُشروا على الإنتاج مع
تحقق كامل بعد النشر. لون الدارك مود الأصلي محفوظ بالظبط بدون أي تغيير —
اللي اتضاف هو خيار إضافي، مش استبدال.
