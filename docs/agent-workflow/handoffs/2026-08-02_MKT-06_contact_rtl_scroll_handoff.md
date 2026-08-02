# MKT-06 — Marketing site: Arabic-only horizontal scroll on /contact

**التاريخ:** 2026-08-02
**المالك:** Mohamed
**المنفذ والمراجع النهائي:** Codex
**الحالة:** COMPLETE

## 1. الخلفية

بعد إغلاق MKT-05، رفع Mohamed screenshot مباشر لصفحة `elkheima.com/ar/contact`
يوضّح مساحة سكرول أفقي فاضية طويلة على يمين الشاشة — نفس الصفحة بباقي
اللغات (`/en`, `/ru`, `/it`) سليمة تمامًا.

## 2. النتيجة

فورم "تواصل معنا" فيه حقل مخفي مضاد للبوتات (honeypot — حقل `website`
لو bot ملاه بيتم رفض الطلب بصمت من الباك إند، زائر حقيقي عمره ما يشوفه
أو يملأه). كان مخفي بتقنية قديمة:

```html
<input v-model="form.website" class="absolute -left-[10000px]" ... />
```

الحقل ده `position: absolute` من غير أي عنصر أب `position: relative`
قريب يحتويه — فبيتموضع نسبةً لأقرب containing block فعلي (تقريبًا
الصفحة كلها). في صفحات LTR (إنجليزي/روسي/إيطالي)، المتصفح عادةً بيمنع
السكرول لإحداثيات سالبة (X < 0) — الحقل بيفضل خارج الشاشة تمامًا من
غير أي أثر ظاهر. لكن في صفحات RTL (عربي)، نقطة بداية السكرول بتتقلب
(بتبدأ من اليمين)، والمتصفحات (خصوصًا عائلة Chromium) فعليًا بتسمح
بالوصول للمنطقة السالبة دي عبر السكرول — يعني عرض الصفحة الفعلي القابل
للسكرول كان بيتوسّع 10000px إضافية، بالظبط زي الـscreenshot.

## 3. الإصلاح

استبدال `class="absolute -left-[10000px]"` بـ`class="sr-only"` — تقنية
Tailwind القياسية (`clip: rect(0,0,0,0); width:1px; height:1px;
overflow:hidden`) بدل إزاحة فيزيائية ضخمة. نفس النتيجة (الحقل مخفي عن
العين والقارئ الصوتي، لسه موجود فعليًا في الـDOM لأي bot ساذج بيملأ كل
الحقول من غير تفرقة) من غير أي احتمال overflow في أي اتجاه (LTR أو RTL).
نفس التقنية دي مستخدمة فعلاً في مكان تاني بالموقع (`PublicContactConsent.vue`).

فحصت باقي الموقع لنفس نمط الإزاحة الفيزيائية الضخمة
(`-left-[Npx]`/`-right-[Npx]`) — التطابق الوحيد التاني كان blob زخرفي
في `CTASection.vue` (`right: -100px`)، لكنه محاط فعليًا بعنصر أب
`position: relative; overflow: hidden` — محتوى بأمان، مش نفس الباج.

## 4. المصدر

- repo: `elkheima-marketing-website` (منفصل)
- branch: `main`
- commit: `1371975`
- الملف المتغيّر: `src/apps/public/Contact.vue`

## 5. بوابة الجودة

- `npm run validate` (public-truth check + `vue-tsc --noEmit` + `vite
  build`) نضاف.
- تحقّق مباشر من الحاوية الحية بعد النشر: جلب bundle الإنتاج المنشور
  فعليًا (`public-pages-*.js`) وتأكيد صفر تكرار لـ`"10000px"` (النمط
  القديم اختفى تمامًا) ووجود `"sr-only"` (النمط الجديد فعّال).
- مفيش أداة browser automation متاحة في هذه الجلسة لأخذ screenshot
  مباشر للتأكيد البصري — الثقة هنا مبنية على: (أ) تشخيص نظري دقيق يطابق
  السلوك الموصوف تمامًا (باج RTL/negative-offset معروف وموثّق)، (ب) نفس
  التقنية البديلة (`sr-only`) شغالة فعليًا في مكان تاني بنفس المستودع،
  (ج) تحقق مباشر من محتوى الـbundle المنشور فعليًا كما فوق.

## 6. النشر

- release: `/opt/elkheima-marketing-releases/1371975`، current symlink
  محدّث.
- archive: `/var/backups/resort-os/marketing-source-releases/1371975.tar.gz`،
  SHA-256 `21fbf305bc06e038464803e1c51703a3b7bcc899e97acfcc35717ac1b061b903`.
- rollback tag: `resort-os-rollback/marketing-site:pre-1371975`، manifest:
  `/var/backups/resort-os/marketing-source-releases/1371975-rollback-image.txt`.
  release القديم `/opt/elkheima-marketing-releases/53bf7a3` لسه موجود
  كامل، مش متحذوف.
- `marketing_site` بس اتبنى واتنشر — resort-os (backend/frontend) متلمسش
  خالص، مفيش migration ولا تغيير DB.
- `sudo docker ps` أكد `RestartCount=0`، صفر error/emerg في اللوجات.
- `https://elkheima.com/ar/contact` و`/en/contact` → 200 الاتنين.
- ملاحظة عملية أثناء النشر: انقطاع SSH مؤقت لثواني وقت خطوة الـtagging
  الأولى — اتحل بإعادة المحاولة العادية، الاتصال رجع فورًا، صفر أثر على
  البيانات أو الحاويات.
