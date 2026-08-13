# دليل الرفع على VPS — تعديل 2FA للموظفين العاديين

**التاريخ:** 2026-08-13  
**التعديل:** جعل 2FA اختياري للموظفين العاديين (cashier, waiter, etc.)  
**Branch:** `claude/CX-02C-frontend-auth-bootstrap`

---

## ملخص التعديلات

تم تعديل النظام علشان 2FA (Google Authenticator) يكون **إجباري بس للأدوار الحساسة**:
- ✅ `super_admin` - مالك النظام
- ✅ `accountant` - المحاسب (بيتعامل مع بيانات مالية)
- ✅ `owner` - مالك عقد الملكية الجزئية

الموظفين العاديين (cashier, waiter, receptionist, chef...) دلوقتي:
- ❌ مش محتاجين Google Authenticator
- ✅ يسجلوا دخول بـ **بريد + كلمة مرور فقط**

---

## خطوات الرفع على VPS

### 1️⃣ على الجهاز المحلي (Local)

```bash
# تأكد إن كل التعديلات متحفوظة
cd /home/wego/projects/resort-os
git status

# شوف آخر commits
git log --oneline -5

# اعمل push للـ branch
git push origin claude/CX-02C-frontend-auth-bootstrap

# (اختياري) لو عايز تعمل merge في main:
git checkout main
git merge claude/CX-02C-frontend-auth-bootstrap
git push origin main
```

---

### 2️⃣ على VPS

#### أ. اتصل بالـ VPS

```bash
# من جهازك المحلي
ssh root@191.218.161.133

# أو لو عندك user تاني:
# ssh resortos@191.218.161.133
```

#### ب. روح لمجلد المشروع

```bash
cd /opt/resort-os
# أو المسار اللي موجود فيه المشروع
```

#### ج. اسحب آخر تعديلات

```bash
# شوف الـ branch الحالي
git branch --show-current

# اسحب التعديلات من الـ branch اللي عامل عليه push
git fetch origin
git pull origin claude/CX-02C-frontend-auth-bootstrap

# أو لو mergت في main:
# git pull origin main

# تأكد إن التعديلات نزلت
git log --oneline -5
```

#### د. (اختياري) عطّل 2FA للموظفين القدام

لو عندك موظفين عاديين **فعّلوا 2FA قبل كده**:

```bash
cd /opt/resort-os/backend
source venv/bin/activate  # أو .venv/bin/activate
python scripts/disable_2fa_for_regular_staff.py
```

الـ script ده هيسألك تأكيد قبل ما يعطّل 2FA.

#### هـ. شغّل الـ deployment script

```bash
cd /opt/resort-os

# لو عايز تنشر branch معين:
DEPLOY_BRANCH=claude/CX-02C-frontend-auth-bootstrap bash scripts/deploy.sh

# أو لو mergت في main:
# DEPLOY_BRANCH=main bash scripts/deploy.sh
```

الـ script ده هيعمل:
1. ✅ نسخة احتياطية من الـ database
2. ✅ Build للـ backend و frontend
3. ✅ تشغيل migrations (لو في)
4. ✅ Restart للـ containers
5. ✅ Health check

#### و. تابع اللوجات

```bash
# شوف لوجات الـ backend
cd /opt/resort-os
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml logs backend --tail=100 -f

# للخروج: Ctrl+C

# شوف حالة كل الـ containers
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml ps
```

---

### 3️⃣ اختبار التعديلات

#### أ. افتح النظام

افتح المتصفح على: `https://191.218.161.133`

#### ب. جرّب تعمل حساب موظف جديد

1. سجّل دخول كـ Super Admin
2. روح **مركز تحكم Super Admin ← تبويب المستخدمين**
3. اختار موظف من الموارد البشرية
4. اختار دور عادي زي `cashier`
5. اضغط **إنشاء الحساب بأمان**
6. لاحظ إن **enrollment_token مش هيظهر** — بس كلمة المرور المؤقتة!

#### ج. جرّب تسجل دخول بالحساب الجديد

1. افتح نافذة خاصة (Incognito)
2. روح `https://191.218.161.133/login`
3. سجّل دخول بـ **البريد + كلمة المرور المؤقتة بس**
4. غيّر كلمة المرور
5. تدخل مباشرة للنظام — **من غير Google Authenticator!** ✅

---

## 🔴 لو حصلت مشكلة

### المشكلة: deploy.sh فشل

```bash
# شوف الخطأ بالظبط
cat /opt/resort-os/scripts/deploy.sh

# جرّب تشغل الخطوات يدوي:
cd /opt/resort-os

# 1. Build
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml build

# 2. Migrations
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml run --rm backend alembic upgrade head

# 3. Up
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml up -d

# 4. شوف اللوجات
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml logs backend --tail=50
```

### المشكلة: Backend مش شغال

```bash
# شوف اللوجات
docker logs resort-os-prod-backend-1 --tail=100

# Restart
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml restart backend
```

### المشكلة: Frontend القديم لسه ظاهر

```bash
# امسح الـ cache
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml restart staff-app

# على المتصفح: Ctrl+Shift+R (hard refresh)
```

---

## ملاحظات مهمة

1. **الـ deployment بيعمل backup تلقائي** قبل أي تغيير
2. **الـ super_admin والـ accountant لسه محميين بـ 2FA** — مفيش تغيير عليهم
3. **الموظفين القدام** اللي فعّلوا 2FA ممكن تعطله بالـ script
4. **مفيش migrations جديدة** — التعديلات بس في الـ code

---

## معلومات الـ VPS

- **IP:** 191.218.161.133
- **User:** root أو resortos
- **Project Path:** `/opt/resort-os` (تأكد من المسار الصحيح)
- **Staff App:** https://191.218.161.133
- **Health Check:** https://191.218.161.133/health

---

## الـ commits اللي هتترفع

```
b9dd5ef - chore: add script to disable 2FA for regular staff
bd8e580 - fix(auth): make 2FA optional for regular staff roles
```

---

**أي استفسار أو مشكلة، ابعتلي! 🚀**
