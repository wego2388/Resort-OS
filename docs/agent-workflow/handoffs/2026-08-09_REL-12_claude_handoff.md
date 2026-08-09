# Handoff — REL-12: PMS checkout/folio settlement fix

**Date:** 2026-08-09
**Agent:** Claude
**Commit:** `403bbd7` — resort-os (`claude/CX-02C-frontend-auth-bootstrap`)
**Status:** Deployed to production, verified

---

## ما اتعمل

إغلاق الفجوة المحاسبية الموثّقة في `PROJECT_STATUS.md` §8.1 (REL-11) —
بتأكيد صريح من محمد على سياسة التشغيل الفعلية: **"الاستقبال بيحصّل كل
حاجة مرة واحدة وقت الخروج"**.

`pms.services._post_checkout_journal` كانت بتقفل بس `booking.total_rate`
(سعر الغرفة) مقابل حساب 1150 (ذمم الفوليو). أي "شحن على حساب الغرفة" من
الشاطئ أو الدايننج (`FolioCharge.charge_type` = `beach`/`dining` — كل
واحدة منها عندها قيد إيراد منفصل خاص بيها اتسجّل وقت الشحن نفسه Dr.1150/
Cr.حساب الإيراد المناسب) كان بيفضل قايم كرصيد مفتوح على 1150 للأبد بعد
الـcheckout، بصمت — بما إن محمد أكّد إن الاستقبال بالفعل بيحصّل كل حاجة
سوا، ده كان معناه القيد المحاسبي مش بيعكس الواقع التشغيلي الفعلي.

**الإصلاح**:
1. بيجمع أي `FolioCharge` لسه `is_settled=False` بـ`charge_type` beach أو
   dining على فوليو الحجز (شامل `vat_amount`/`service_charge`)، ويضيف
   المجموع لمبلغ التسوية.
2. `room_extra` (رسوم وصول مبكر/مغادرة متأخرة) **مش بتتضاف تاني** —
   `request_early_late` أصلاً بتضيفها مباشرة لـ`booking.total_rate`،
   فمتضمّنة بالفعل، بس بتتعلّم `is_settled=True` زي الباقي.
3. الفوليو بيتقفل (`status="closed"`) عشان يعكس إن الحساب اتقفل فعليًا.
4. القفل عبر `finance.crud.lock_folio_for_update` (نفس القفل البلوكينج
   اللي `add_folio_charge` بتاخده قبل أي شحنة جديدة) — يمنع سباق حقيقي:
   لو شحنة "charge to room" شغالة بالظبط وقت الـcheckout، الـcheckout
   بينتظرها تخلص الأول بدل ما ياخد صورة ناقصة للفوليو ويقفله فوقها.

**قرار موثّق صراحةً في الكود**: مفيش استدعاء لـ`finance.services.
settle_folio` الموجودة بالفعل — دالة `can_checkout` جوّاها بترفض أي
فوليو عليه أي شحنة أصلاً (`unsettled_amount > 0`) **قبل** ما تتسوّى، يعني
الدالة دي مش موصولة بأي مسار حقيقي في المشروع فعليًا من الأساس (كل شحنة
بتتولد بـ`is_settled=False` افتراضيًا وحاجة تانية ماكانتش بتغيّر ده قبل
كده) — فجوة منفصلة تمامًا، برّه نطاق الإصلاح ده.

**تست جديد**: `test_checkout_settles_room_charged_beach_and_dining_extras`
(`tests/test_api/test_pms.py`) — فوليو فيه شحنة شاطئ (300 + 42 ضريبة)
وشحنة دايننج (150)، بعد checkout: القيد المحاسبي الواحد بيقفل
`room_total + 300 + 42 + 150` بالظبط، الشحنتين بقوا `is_settled=True`،
والفوليو `status="closed"`.

**لا migration** — Alembic head `d0e1f2a3b4c5` بدون تغيير.

---

## Validation ✅ (محلي، قبل أي نشر)

```
cd backend && .venv/bin/pytest tests/ -q       → 100% (صفر F/E)، exit 0
  (3 دورات كاملة — قبل وبعد إضافة القفل، ومرة أخيرة نهائية)
cd backend && .venv/bin/alembic heads          → d0e1f2a3b4c5 (head)
git diff --check                                → نظيف
```

---

## خطوات النشر المنفَّذة (DEPLOYMENT.md §5)

نطاق backend فقط — `el_kheima` اتبنى برضو (نفس مصدره بالظبط زي `92aa769`
بدون تغيير) عشان كل الخدمات المستبدلة تفضل على نفس commit الـrelease
بالظبط، لا فرق فعلي. `marketing_site`/`owner` متلمسوش خالص.

```
COMMIT=403bbd7
git archive → sha256 41835375... → scp → verify checksum على الـVPS
  (مطابق تمامًا)
extract → /opt/resort-os-releases/403bbd7 (جديد)
نسخ backend/.env.prod من الإصدار الفعّال (92aa769) بصلاحية 0600
python3 scripts/validate_prod_env.py → passed
tag rollback images لكل الـ6 خدمات → pre-403bbd7
  (/var/backups/resort-os/source-releases/403bbd7-rollback-images.txt)
pre-release DB backup → resort_os_20260809_124603.dump (620K)
  اتحقق منه فعليًا: docker cp → pg_restore --list → 1472 TOC entry
docker compose build backend celery_worker celery_beat el_kheima → نجح
preflight: python -c 'from app.main import app; print(app.title)' → El Kheima Beach
alembic heads/upgrade head → d0e1f2a3b4c5 (head)، لا migration
staged replacement (كل مرحلة healthy قبل التالية):
  up -d --no-deps backend                → healthy خلال ~12 ثانية
  up -d --no-deps celery_worker celery_beat → healthy فورًا
  up -d --no-deps el_kheima               → healthy فورًا
  up -d --no-deps --force-recreate nginx  → up
ln -sfn /opt/resort-os-releases/403bbd7 /opt/resort-os-current
```

---

## Post-deploy acceptance ✅

```
docker ps → كل الحاويات المستبدلة healthy، صفر restart
curl -fsSI https://elkheima.com/        → HTTP/2 200
curl -fsSI https://www.elkheima.com/    → HTTP/2 200
curl -fsSI https://app.elkheima.com/    → HTTP/2 200
curl -fsS  https://app.elkheima.com/health
  → {"status":"ok", database: ok (8.7ms), redis: ok (1.4ms)}
working_dir label (backend + el_kheima) = /opt/resort-os-releases/403bbd7  ✅
RestartCount = 0 لكل الخدمات المستبدلة                                     ✅
alembic current = d0e1f2a3b4c5 (head)                                      ✅
DB sanity: users=5, branches=1 — نفس البيانات الحقيقية                     ✅
backend/celery_worker/nginx logs → صفر traceback/critical/fatal            ✅
مفيش قاعدة بيانات استرجاع مؤقتة اتسابت                                     ✅
```

---

## Rollback (لو حاجة وحشت)

```bash
docker tag resort-os-rollback/backend:pre-403bbd7 \
  resort-os-prod-backend:latest
docker tag resort-os-rollback/celery-worker:pre-403bbd7 \
  resort-os-prod-celery_worker:latest
docker tag resort-os-rollback/celery-beat:pre-403bbd7 \
  resort-os-prod-celery_beat:latest
docker tag resort-os-rollback/el-kheima:pre-403bbd7 \
  resort-os-prod-el_kheima:latest
docker tag resort-os-rollback/nginx:pre-403bbd7 \
  resort-os-prod-nginx:latest

cd /opt/resort-os-releases/92aa769
docker compose --env-file backend/.env.prod \
  -f docker-compose.prod.yml -f docker-compose.prod.domain.yml \
  up -d --no-deps backend celery_worker celery_beat el_kheima nginx

sudo ln -sfn /opt/resort-os-releases/92aa769 /opt/resort-os-current
```

---

## ملاحظات

- **لا migration** — Alembic head بدون تغيير.
- **`marketing_site`/`owner` متلمسوش خالص**.
- فجوة `finance.services.settle_folio`/`can_checkout` غير قابلة
  للاستخدام فعليًا (تفصيلها فوق) **لسه موجودة، برّه نطاق هذه الدفعة** —
  مذكورة هنا كمرجع لو حد احتاجها لاحقًا.
- هذه آخر فجوة موثّقة كانت مفتوحة في `PROJECT_STATUS.md` §8.1 — القسم
  ده دلوقتي تاريخي (يوثّق الاكتشاف الأصلي)، الإصلاح موصوف في REL-12 هنا.
