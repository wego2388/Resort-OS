# Handoff — RBAC-ADMIN-01: /admin nav/guard permission fix

**Date:** 2026-08-08
**Agent:** Claude
**Commit:** `f322296` — resort-os (`claude/CX-02C-frontend-auth-bootstrap`)
**Status:** Deployed to production, verified

---

## ما اتعمل

إصلاح لعيبين حقيقيين في نظام الصلاحيات الخاص بقسم `/admin` في تطبيق
`el-kheima` (اتكشفوا كتعديلات محلية غير محفوظة، اتراجعوا وتم commit
بعد تحقق كامل):

1. **فلتر القائمة الجانبية (`BackOfficeLayout.vue`) كان بيتجاهل
   `requiredPermission` كل ما `requiredRoles` موجودة** — كان بيرجع
   النتيجة فورًا من غير ما يوصل لفحص الصلاحية التفصيلية. مثال حقيقي:
   رابط الحسابات الائتمانية كان بيظهر لأي دور مسموح بيه الدور نفسه
   بغض النظر عن منحه `credit.accounts:view` فعليًا من عدمه.
2. **تعارض بين القائمة وحارس التنقل (`router/index.ts`)** — الأب
   `/admin` كان مقفول بمستوى (level ≥60)، فـ`supervisor` (مستوى 50)
   كان يشوف روابط الصيانة/التأجير في القائمة (لأنها كانت مُعرَّفة
   `requiredRole: 'supervisor'` على مستوى العنصر) لكن أي ضغطة عليها
   كانت بترجّعه بعيد فورًا لأنه ما يعديش بوابة الأب. اتصلح بـ
   `requiredRoles` صريحة على كل مسار/عنصر تطابق الدور المطلوب فعليًا
   لكل شاشة، بدل الاعتماد على المستوى العددي وحده.

**ملف واحد إضافي** اتعمله commit ضمن نفس الدفعة: handoff موثّق لصفحة
تسويقية (`MKT-SS-01`) كانت untracked في المستودع.

---

## Validation ✅ (محلي، قبل أي نشر)

```
pnpm --filter el-kheima type-check   → نضاف
pnpm --filter el-kheima build        → نضاف
pnpm --filter el-kheima test:frontend → 95 اختبار، كلهم عدّوا
                                        (يشمل authRoleGuard.spec.ts
                                        وsmoke/router.spec.ts مباشرة)
pnpm run type-check:all / build:all  → نضاف (el-kheima + owner)
bash scripts/agent-check.sh --quick  → نضاف (alembic head واحد،
                                        2569 اختبار متجمّعين، compose
                                        configs صحيحة)
cd backend && pytest tests/ -v       → 2526 عدّوا، 43 skipped،
                                        صفر فشل (477s) — الباك إند ملوش
                                        أي تعديل في هذه الدفعة، اتشغّل
                                        كبوابة كاملة زي ما DEPLOYMENT.md
                                        بيطلب قبل أي إصدار
```

---

## خطوات النشر المنفَّذة (DEPLOYMENT.md §5)

نطاق frontend فقط — الباك إند/سيليري ملهمش أي تعديل كود بين الإصدار
السابق (`eda6617`) وده، فاتبنى `el_kheima` بس.

```
COMMIT=f322296
git archive → sha256 → scp → verify checksum على الـVPS (مطابق تمامًا)
extract → /opt/resort-os-releases/f322296 (جديد، مالوش وجود قبل كده)
نسخ backend/.env.prod من الإصدار الفعّال (eda6617) بصلاحية 0600
python3 scripts/validate_prod_env.py → passed
tag rollback images لكل الـ6 خدمات → pre-f322296
  (منفَّذ في /var/backups/resort-os/source-releases/f322296-rollback-images.txt)
pre-release DB backup → resort_os_20260808_223917.dump (616K)
  اتحقق منه فعليًا: docker cp للحاوية → pg_restore --list →
  1472 TOC entry، Format: CUSTOM — أرشيف صالح
docker compose build el_kheima → نجح
staged replacement:
  up -d --no-deps el_kheima       → healthy خلال 20 ثانية
  up -d --no-deps --force-recreate nginx → up
ln -sfn /opt/resort-os-releases/f322296 /opt/resort-os-current
```

Backend/celery/postgres/redis **متلمسوش خالص** — لسه على نفس الإصدار
(`eda6617`) بالظبط، زي ما DEPLOYMENT.md بيطلب لإصدار frontend-only.

---

## Post-deploy acceptance ✅

```
docker ps → كل الحاويات healthy/Up، صفر restart
curl -fsSI https://elkheima.com/        → HTTP/2 200
curl -fsSI https://www.elkheima.com/    → HTTP/2 200
curl -fsSI https://app.elkheima.com/    → HTTP/2 200
curl -fsS  https://app.elkheima.com/health
  → {"status":"ok", database: ok (1.6ms), redis: ok (2.1ms)}
working_dir label (el_kheima) = /opt/resort-os-releases/f322296  ✅
RestartCount = 0                                                  ✅
TLS SAN = app.elkheima.com, elkheima.com, owner.elkheima.com, www.elkheima.com ✅
el_kheima + nginx logs → صفر traceback/critical/fatal
مفيش قاعدة بيانات استرجاع مؤقتة اتسابت
```

**تأكيد إضافي غير مخطَّط**: أثناء النشر كان فيه جلسة مستخدم حقيقية شغالة
فعليًا (`/admin/finance`، WebSocket alerts/shifts) — الطلبات كلها كملت
200/101 من غير أي انقطاع أو خطأ ملحوظ في اللوج أثناء استبدال الحاوية.

---

## Rollback (لو حاجة وحشت)

```bash
docker tag resort-os-rollback/el_kheima:pre-f322296 \
  resort-os-prod-el_kheima:latest
docker tag resort-os-rollback/nginx:pre-f322296 \
  resort-os-prod-nginx:latest

cd /opt/resort-os-releases/eda6617
# (نفس نمط استخراج DB_PASSWORD ثم)
docker compose --env-file backend/.env.prod \
  -f docker-compose.prod.yml -f docker-compose.prod.domain.yml \
  up -d --no-deps el_kheima nginx

sudo ln -sfn /opt/resort-os-releases/eda6617 /opt/resort-os-current
```

---

## ملاحظات

- **لا migration** — مفيش تعديل في الباك إند أو قاعدة البيانات خالص.
- **لا restart لـbackend/celery** — بناء واستبدال `el_kheima` + إعادة
  إنشاء `nginx` بس.
- كل الأدوار الجديدة/المُعاد نطاقها (`supervisor`، `accountant`،
  `hr_manager` على شاشات محدَّدة) موجودة بالفعل في `ROLE_LEVELS` —
  مفيش دور جديد اتضاف.
