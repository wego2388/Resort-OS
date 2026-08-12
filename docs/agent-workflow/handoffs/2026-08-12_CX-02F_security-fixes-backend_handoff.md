# Handoff — CX-02F: إصلاح ثغرات أمنية في الـ backend
**التاريخ:** 2026-08-12
**الـ Branch:** `claude/CX-02C-frontend-auth-bootstrap`
**آخر commit:** `544aa1a`
**الحالة:** مُنشور على الإنتاج ✅ (backend + celery healthy)

---

## الثغرات التي اكتُشفت وأُصلحت

### 🔴 1. Beach WebSocket — IDOR / Branch Isolation مفقود
**الملف:** `backend/app/modules/beach/api/router.py`

`/beach/ws/map/{branch_id}` كان بيتحقق من الـ token والمستوى فقط (كاشير+)، بدون فحص إن الـ branch_id في الـ URL هو فرع المستخدم نفسه.

**التأثير:** كاشير فرع A يقدر يشترك في البث الحي لخريطة فرع B — تشيك-إن/أوت + أماكن الضيوف في الوقت الفعلي — بمجرد تغيير رقم الفرع في الـ URL.

**الإصلاح:** إضافة `assert_branch_access` بعد `get_websocket_user`، يغلق بـ 4403 لو المستخدم مش من نفس الفرع. نفس النمط المطبّق على alerts/dining/analytics WebSockets.

---

### 🔴 2. Image Upload — Content-Type Spoofing
**الملف:** `backend/app/modules/dining/api/router.py`

`upload_item_image` كان يتحقق من الـ `content_type` header فقط — اللي المستخدم يتحكم فيه بالكامل. ممكن يرفع ملف تنفيذي (PHP/EXE) بـ `image/jpeg` في الـ header.

**الإصلاح:** فحص magic bytes فعلية من محتوى الملف:
- JPEG: `\xff\xd8\xff`
- PNG: `\x89PNG\r\n\x1a\n`
- WebP: `RIFF????WEBP`

---

### 🟡 3. Excel Import — Zip Bomb / DoS
**الملفان:** `backend/app/modules/hr/services.py` + `backend/app/modules/timeshare/services.py`

`openpyxl.load_workbook()` كان بيشتغل بدون حد أقصى للحجم — ملف xlsx مضغوط بـ 1 MB ممكن يفتح لـ 500+ MB في الذاكرة.

**الإصلاح:** فحص `len(file_content) > 5 MB` قبل `load_workbook()` في الاتنين.

---

## الفحوصات

```bash
.venv/bin/pytest tests/  # ✅ 2748 passed, 68 skipped
bash scripts/sync-deploy.sh resort-os backend,celery_worker,celery_beat  # ✅ healthy
curl https://app.elkheima.com/api/v1/auth/me  # ✅ 401 (auth required — صح)
curl https://app.elkheima.com/admin/super-admin  # ✅ 200
```

---

## الحالة الحالية للإنتاج
- Backend commit: `544aa1a` ✅
- Frontend commit: `52819a7` (لم يتغير) ✅
- كل الخدمات `healthy` ✅
- لا migrations — Alembic head: `d1e2f3a4b5c6`

---

## ما يظل للمراجعة (غير حرج)
- image upload: يمكن إضافة فحص حجم على الـ router level (قبل `await file.read()`) في الـ HR upload لو احتجنا لاحقاً
- Excel rows limit: ممكن نضيف حد أقصى لعدد الصفوف في `iter_rows` لو الـ files كبيرة جداً
