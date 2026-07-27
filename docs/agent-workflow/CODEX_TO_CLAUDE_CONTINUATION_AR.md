# نقطة استئناف Claude بعد Codex — El Kheima

**آخر تحديث:** 2026-07-26 22:35 Africa/Cairo  
**الهدف:** تمكين Claude من مواصلة التنفيذ فور انتهاء حصة Codex، بلا إعادة
عمل أو تخمين أو اعتماد على ملخص المحادثة.  
**حالة Git:** لا commit ولا push. نُشرت لقطة exact من الـworktree على
`191.218.161.133`، موثقة في VPS-02، وكل التغييرات المحلية ما زالت مقصودة
ومشتركة.

## 1. أمر الاستئناف الذي يُعطى لـClaude

```text
اقرأ AGENTS.md ثم CLAUDE.md بالكامل، ثم
docs/agent-workflow/CODEX_TO_CLAUDE_CONTINUATION_AR.md،
docs/agent-workflow/EL_KHEIMA_EXECUTION_BOARD.md،
وأحدث handoffs المذكورة في checkpoint. افحص git status وgit diff الفعليين.
لا تعِد تنفيذ الحزم المكتملة، لا تستخدم app.seed في production، لا تفعّل
الشات في production، ولا تعمل commit/push/deploy قبل بوابات التحقق المكتوبة.
استلم أول بند IN_PROGRESS أو NEXT في checkpoint، وحدّث هذا الملف بعد كل Gate.
```

## 2. قواعد لا يجوز التراجع عنها

1. الاسم التجاري: **El Kheima Beach**.
2. الشات non-blocking و`CHATBOT_ENABLED=false` افتراضيًا. لا يُفعّل لمجرد
   أن Gemini يرد؛ يلزم Host map وRedis وgovernance وapproved facts وUAT.
3. لا raw chat retention في DB أو browser، ولا branch/location من body.
4. لا `branch_id ?? 1` أو أول فرع أو client-selected protected branch.
5. membership هي مصدر صلاحية الفروع؛ active branch مربوط بعائلة
   refresh/session وليس قيمة user-global.
6. `app.seed` development/testing فقط. لا حسابات demo ولا ضيوف/غرف/أسعار
   ملفقة في الإنتاج.
7. قرار المستخدم الناسخ: لا تعتمد على `elkheimabeachresort.com` أو أي DNS.
   أصل التشغيل العام هو `191.218.161.133` فقط، وpublic truth تظل
   fail-closed بلا بيانات مالك معتمدة.
8. production compose اسمه `resort-os-prod` ولا fallback لكلمة مرور DB.
9. لا تلمس `backend/.env.prod` بما يعرض قيمًا، ولا تطبعه أو تنقله خارج SSH
   المشفر. الملف ignored وmode `0600`.
10. لا تُنشَر الحالة غير committed على أنها SHA `27cc217`. أي staging من
    worktree يحتاج exact source manifest واضح.

## 3. الحزم المكتملة — لا تعِدها

| الحزمة | النتيجة | الدليل |
|---|---|---|
| الخطة النهائية | High/Medium/Low وخطة frontend/backend/DB/VPS | `docs/audits/EL_KHEIMA_FINAL_EXECUTION_PLAN_AR.md` |
| CX-03 | QR/PWA staff identity isolation وproduction public URL | `handoffs/2026-07-26_CX-03_codex_handoff.md` |
| CX-02A | PMS fine-grained permissions | `handoffs/2026-07-26_CX-02A_codex_handoff.md` |
| CX-02B | PMS branch/object isolation + WS 4403 | `handoffs/2026-07-26_CX-02B_codex_handoff.md` |
| CL-01R | chat stateless/fail-closed، High/Medium مغلقة | `handoffs/2026-07-26_CL-01R_codex_handoff.md` |
| DB-01 | Alembic fresh PostgreSQL chain blocker fixed | `handoffs/2026-07-26_DB-01_codex_handoff.md` |
| CL-02A/D | marketing truth containment, SW retirement, headers, dependencies | `handoffs/2026-07-26_CL-02AD_codex_handoff.md` |
| VPS-01 | Hostinger access/base hardening/TLS/firewall/snapshot | `handoffs/2026-07-26_VPS-01_codex_handoff.md` |
| CX-02C | branch memberships/session active branch/backend bootstrap | `handoffs/2026-07-26_CX-02C_codex_handoff.md` |
| CL-02B | contact/CRM privacy contract and encrypted PII | `handoffs/2026-07-26_CL-02B_codex_handoff.md` |
| CL-02C | denied-by-default analytics consent and IP-only truth | `handoffs/2026-07-26_CL-02C_codex_handoff.md` |
| VPS-02 | exact-source IP-only production deployment | `handoffs/2026-07-26_VPS-02_ip_deployment_codex_handoff.md` |

آخر تحقق مستقل معروف:

- Chat: `25 passed`.
- Chat + Gate 8: `69 passed` في handoff.
- DB-01 PostgreSQL الحقيقي: `3 passed` في handoff؛ التشغيل العادي بدون admin
  DSN يظهر `1 passed, 2 skipped` كما هو مقصود.
- Marketing بعد CL-02A/D:
  `npm run validate` PASS، `npm audit` صفر، build 2040 modules.
- `bash scripts/agent-check.sh` PASS.
- Full backend النهائي: `2151 passed, 38 skipped, 0 failed`.
- Alembic production head: `c4d8e2f6a901`.
- Marketing النهائي: validate/build/typecheck PASS وnpm audit صفر.

## 4. الحزم الجارية عند هذا checkpoint

لا توجد حزمة تنفيذ موازية مفتوحة. أُوقفت الوكلاء قبل أخذ لقطة النشر حتى لا
تتغير الشجرة أثناء النقل والبناء. لا تبدأ مهمة كبيرة جديدة قبل إنهاء
bootstrap/UAT أو طلب Mohamed الصريح.

## 5. حالة الـVPS الخارجية — لا تظهر في Git

- VM ID `1856853`, IP `191.218.161.133`.
- SSH alias: `resort-os-vps`, user `resortos`, key-only.
- root login/password auth مغلقان، exposed root password تم تدويره.
- Ubuntu محدث، kernel `6.8.0-136-generic`, لا reboot pending.
- Fail2ban وUFW يعملان.
- Hostinger firewall `335259` مربوط بالـVM. ما زال يحتوي allow تاريخيًا
  لـ`8081`، لكن UFW يمنعه ولا يوجد listener عليه. المنافذ الفعلية
  `22,80,443,8443`.
- Docker `29.6.2`, Compose `v5.3.1`.
- شهادة Let's Encrypt موثوقة للـIP `191.218.161.133` حتى `2026-08-02`
  (short-lived)، وتجديد webroot اختُبر بنجاح.
- snapshot مؤقت `314805` ينتهي `2026-07-27T18:43:33Z`.
- مشروع Compose `resort-os-prod` منشور: 8 containers، كلها running، كل
  healthchecks المعرفة ناجحة، وصفر restart.
- المسارات الجاهزة:
  `/opt/resort-os`, `/opt/elkheima-marketing-website`,
  `/var/backups/resort-os`, `/var/www/certbot`.
- واجهة الموظفين: `https://191.218.161.133`.
- التسويق: `https://191.218.161.133:8443`.
- backup timer وcertificate timer فعالان؛ backup→restore drill نجح.
- users=0، branches=0، demo users=0؛ لم يُشغّل `app.seed`.
- الدومين خارج مسار الإطلاق بقرار المستخدم، ولا توجد خطوة DNS.

مرجع كامل وحديث:
`handoffs/2026-07-26_VPS-02_ip_deployment_codex_handoff.md`.

## 6. NEXT بعد الحزم الجارية

1. Mohamed ينشئ named Super Admin تفاعليًا ويكمل password change + 2FA
   بدون مشاركة الأسرار مع الوكيل.
2. إنشاء أول فرع معتمد وربط Host الـIP به؛ بعدها فقط اختبر contact intake.
3. **CX-02C frontend:** auth store/bootstrap/branch selector، route gate،
   offline queue v3 user+branch+module، وإزالة كل fallback.
4. **CL-02G public contract:** `/public/bootstrap` وcatalog غرف/أسعار/توافر
   aggregate مع `as_of` وcurrency/policy، بلا room-level occupancy.
5. **CX-04 production data:** dry-run/import/reconciliation/provenance؛ لا
   أسعار أو balances بلا اعتماد.
6. UAT جهاز/متصفح وتشغيل حقيقي، off-server backup، monitoring/alerts.
7. CL-02F/H وMedium/Low المؤجلة.

لا تعِد build/deploy الحالي لمجرد الاستئناف؛ افحص الخدمة أولًا. لا تضف خطوة
DNS إلا إذا غيّر Mohamed قرار IP-only صراحةً.

## 7. أوامر checkpoint

```bash
cd /home/wego/projects/resort-os
git status --short --branch
bash scripts/agent-check.sh
cd backend
.venv/bin/alembic heads

cd /home/wego/projects/elkheima-marketing-website
npm run validate
npm audit
git diff --check

ssh resort-os-vps 'hostname; sudo -n sshd -T | grep -E \
"^(permitrootlogin|passwordauthentication|authenticationmethods|allowusers)"'
```

لا تشغّل full suite أثناء وجود full pytest آخر. افحص `ps` أولًا. لا تنشر
قبل handoffs النهائية ونجاح Gate الشامل.
