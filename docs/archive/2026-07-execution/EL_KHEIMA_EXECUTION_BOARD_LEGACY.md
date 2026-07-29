# لوحة تنفيذ الخطة النهائية للخيمة

**آخر تحديث:** 2026-07-29 — Codex (final code review + direct VPS audit)
**الخطة:** `docs/audits/EL_KHEIMA_FINAL_EXECUTION_PLAN_AR.md`
**البروتوكول:** `docs/agent-workflow/DUAL_AGENT_EXECUTION_PROTOCOL_AR.md`
**المرحلة الحالية:** local finalization + production source reconciliation؛ IP-only online

> **Checkpoint ناسخ:** الحالة التفصيلية الأحدث في
> `CODEX_TO_CLAUDE_CONTINUATION_AR.md` وتسليم
> `handoffs/2026-07-26_VPS-02_ip_deployment_codex_handoff.md`. الأقسام
> التاريخية أدناه لا تعيد فتح ملكية ملفات أو مهام انتهت.

## Checkpoint ناسخ — Codex 2026-07-29

- المالك أكد: فرع تشغيلي واحد للخيمة؛ لا UI لتبديل الفروع.
- Codex هو قائد التنفيذ والمراجع النهائي، وهو متصل فعليًا بالـVPS بالمفتاح وصلاحيات sudo/Docker.
- الاختبارات المحلية النهائية خضراء؛ حزمة frontend/auth/offline queue جاهزة محليًا.
- الإنتاج healthy على 8 حاويات، لكن `/opt/resort-os` شجرة غير نظيفة عند `0a13c97`؛ النشر متوقف لحفظ ومصالحة exact state.
- شهادة IP قابلة للتجديد؛ dry-run ناجح. لا يوجد مبرر تقني لفرض domain قبل قرار المالك.
- Hostinger provider snapshots/backups = 0؛ offsite recovery ما زال شرطًا مفتوحًا.

> Codex يحدّث حالة Codex والتكامل. أقسام الوكلاء الأقدم سجل تاريخي ولا تتقدم على هذا checkpoint.

## الحالة الإجمالية

| Gate | الحالة | المنفذ الرئيسي | شرط الانتقال |
|---|---|---|---|
| Gate 0 baseline | COMPLETE | Codex | full gates ناجحة |
| Gate 1 auth/branches | CODE COMPLETE — LOCAL FINAL REVIEW | Codex | reconcile source ثم controlled deploy |
| Gate 2 QR/PWA/public contract | HANDOFF جزئيًا | Codex | مراجعة CX-03 ثم عقد public API في حزمة لاحقة |
| Gate 3 marketing/chat security | DEPLOYED CONTAINMENT | Codex | chat off؛ consent/truth fail-closed |
| Gate 4 content/SEO truth | PARTIAL | Codex | بيانات مالك معتمدة؛ لا domain dependency |
| Gate 5 production data | DEFERRED | Codex | ملفات master data واعتماد المالك |
| Gate 6 VPS access/hardening | COMPLETE + REVERIFIED | Codex | key/sudo/SSH policy/UFW/Fail2ban verified |
| Gate 7 deploy/backup/monitoring | PARTIAL / DEPLOY PAUSED | Codex | dirty source reconciliation + offsite + monitoring |
| Gate 8 IP TLS/UAT | PARTIAL | Codex | TLS renewal verified؛ device/business UAT باقي |
| Gate 9 cutover | PAUSED — IP-ONLY | Codex | لا DNS/domain switch دون قرار صريح جديد من Mohamed |

> شهادة IP الحالية تنتهي 2026-08-02، لكن Certbot dry-run نجح والمؤقت كل 12 ساعة؛ domain ليس شرط تجديد.
> **الخطة التفصيلية:** `docs/audits/EL_KHEIMA_DOMAIN_LAUNCH_PLAN_AR.md`

## حالة Claude — يحررها Claude فقط

- **Packet:** CL-01
- **Status:** HANDOFF
- **Base SHA:** `resort-os` @ `27cc217` (main، ahead of origin by 9)، `elkheima-marketing-website` @ `74c66f4` (main، بتاريخ HEAD الحالي)
- **Worktree:** لا يوجد — نفس working directory الرئيسي (لاحظت وجود تعديلات Codex غير committed جارية بالتوازي في `frontend/apps/el-kheima/**`، `docker-compose.prod.yml`، `.github/workflows/ci.yml` وغيرها — **متلمستهاش خالص**، خارج نطاق CL-01 بالكامل)
- **Outcome:** الشات بوت شغّال end-to-end بمنطق أمني/تكلفة كامل (rate limit بالدقيقة + سقف يومي + circuit breaker)، مُختبر حي فعليًا بـGemini API حقيقي (مش mock بس)، صفر بيانات ضيف بترسل للنموذج، XSS حقيقي في رندر رد الشات بوت اتصلح.
- **المستودعات:** `resort-os` و`elkheima-marketing-website`
- **التسليم الكامل:** `docs/agent-workflow/handoffs/2026-07-26_CL-01_claude_handoff.md`
- **Shared files claimed:** `main.py`, `config.py`, `rate_limit.py`, `.env.example`, Alembic/chat migration — **تتحرر الآن لـCodex** (CX-01 review).
- **لا تعدل الآن:** انتهى — Codex يقدر يبدأ CX-01 review على الملفات دي.

## حالة Codex — يحررها Codex فقط

- **Packet:** CX-02C-FE-FINAL + VPS-03
- **Status:** LOCAL_VERIFIED / VPS_ADMIN_CONNECTED / DEPLOY_PAUSED_FOR_SOURCE_RECONCILIATION
- **Base branch/SHA:** `claude/CX-02C-frontend-auth-bootstrap` @ `598938e` مع worktree مقصود غير committed.
- **Outcome:** عقد bootstrap والصلاحيات وsingle-branch UX وoffline identity عُزلت واختُبرت؛ VPS healthy وآمن، والنسخ/TLS تحققا حيًا.
- **Current handoff:** `handoffs/2026-07-29_VPS-03_codex_handoff.md`.
- **Production writes:** لا deploy ولا DNS ولا تعديل أسرار؛ Certbot dry-run فقط. ملف المستخدم `scripts/wait-dns-then-switch.sh` لم يُلمس.

### سجل VPS-02 السابق

- **Packet:** VPS-02
- **Status:** DEPLOYED_IP_ONLY
- **Base branch:** `main`
- **Live:** `https://191.218.161.133` و
  `https://191.218.161.133:8443`
- **Outcome:** exact-source release يعمل على 8 containers، PostgreSQL عند
  `c4d8e2f6a901`، TLS IP وتجديده والنسخ/الاسترجاع اختُبرت. لا users أو
  branches أو demo data؛ bootstrap/UAT مؤجلان.
- **Current handoff:**
  `docs/agent-workflow/handoffs/2026-07-26_VPS-02_ip_deployment_codex_handoff.md`
- **Latest decision:** لا تعتمد على `elkheimabeachresort.com`؛ IP فقط.
- **Commit/push:** لا.

### سجل CX-02B التاريخي

- **Outcome:** عزل PMS بالفرع والـobject مكتمل كـsingle-branch containment:
  كل endpoint داخلي يثبت الصلاحية والفرع، مسارات ID تمنع موارد الفرع
  الآخر، WebSocket يغلق بـ4403، والعلاقات المتقاطعة بين room/customer/
  rate-plan/employee تُرفض قبل الكتابة. الحساب غير المرتبط بفرع يفشل
  مغلقًا، وsuper-admin وحده عالمي.
- **Code scope:**
  - `backend/app/modules/pms/{api/router.py,services.py}`
  - permission branch resolution/action schema في Core/Auth
  - اختبارات PMS/permissions فقط.
- **Shared files claimed:** auth/Core/PMS محررة الآن للمراجعة؛ لم تُلمس ملفات
  chat/config/rate-limit/main/Alembic أو موقع التسويق.
- **Validation:** 58 اختبار PMS، و96 اختبار PMS/permissions/control-plane،
  ثم 2,132 اختبارًا لكل الباك إند عدا ملف chat المتحرك — صفر failures.
  compileall و`git diff --check` ناجحان.
- **VPS writes performed:** لا.
- **SSH:** الخادم يستجيب، والمفتاح الحالي رُفض؛ لم تُستخدم كلمة المرور الظاهرة.
- **Hostinger MCP:** غير متصل بعد؛ ينتظر OAuth/تهيئة Node 24 في مرحلة التنفيذ.
- **Started at:** 2026-07-26.
- **Current handoff:** `docs/agent-workflow/handoffs/2026-07-26_CX-02B_codex_handoff.md`
- **Chat review:** `docs/agent-workflow/handoffs/2026-07-26_CL-01_codex_review.md`
  ما زالت `CHANGES_REQUESTED` حتى تسليم CL-01R.
- **Previous handoffs:**
  - `docs/agent-workflow/handoffs/2026-07-26_CX-02A_codex_handoff.md`
  - `docs/agent-workflow/handoffs/2026-07-26_CX-03_codex_handoff.md`
- **Next:** مراجعة CL-01R فور تسليم Claude. بعد استقرار chat migration يبدأ
  CX-02C لجدول multi-branch memberships وعقد bootstrap وإزالة
  `branch_id ?? 1` من الواجهة، دون إنشاء Alembic head متوازٍ الآن.

## ملكية الملفات المشتركة الحالية

| الملف/النطاق | المالك الحالي | يتحرر عند |
|---|---|---|
| `backend/app/modules/chat/**` | Claude | قبول CL-01 |
| chat Alembic migration | Claude | تسليم CL-01 ثم مراجعة Codex |
| `backend/app/main.py` | Claude | تسليم CL-01 |
| `backend/app/core/config.py` | Claude | تسليم CL-01 |
| `backend/app/core/rate_limit.py` | Claude | تسليم CL-01 |
| marketing chatbot files | Claude | قبول CL-01 |
| `frontend/apps/el-kheima/**` | Codex في CX-03 | بعد Gate 0 |
| auth/PMS/branch membership | Codex في CX-02 | بعد Gate 0 |
| production data/import | Codex في CX-04 | بعد CX-02 |
| compose/deploy/VPS/DNS | Codex في CX-05/CX-06 | بعد الوصول والموافقات |

## العقود المطلوبة قبل التوازي

- [x] Chat endpoint contract من CL-01 — راجع `docs/agent-workflow/handoffs/2026-07-26_CL-01_claude_handoff.md`.
- [ ] `/api/v1/public/bootstrap` contract يقوده Codex ويراجعه Claude.
- [ ] branch/auth bootstrap contract يقوده Codex ويراجعه Claude.
- [ ] content facts schema يقوده Claude ويراجعه Codex.
- [ ] production import format يقوده Codex ويعتمده المالك/المحاسب.

## قرارات/مدخلات مطلوبة من المالك

| القرار | الحالة | يمنع |
|---|---|---|
| النطاق النهائي وملكيته | غير مطلوب لهذه النسخة | قرار IP-only |
| Hostinger OAuth أو إضافة SSH public key | مكتمل | — |
| اعتماد الاسم ووسائل الاتصال | مطلوب | contact/public truth |
| ملفات master data | مطلوب | production import |
| اعتماد الضرائب والأرصدة | مطلوب | المالية والإطلاق |
| ممثلو UAT وGo/No-Go | مطلوب قبل staging | قبول الإنتاج |

## سجل التسليم

تضاف الملفات الجديدة تحت `docs/agent-workflow/handoffs/` بصيغة:

```text
YYYY-MM-DD_<packet-id>_<implementer>_handoff.md
YYYY-MM-DD_<packet-id>_<reviewer>_review.md
```

| الحزمة | تسليم المنفذ | مراجعة | النتيجة |
|---|---|---|---|
| PLAN-01 | هذه الوثائق | بانتظار اعتماد المالك | HANDOFF |
| CL-01 | `2026-07-26_CL-01_claude_handoff.md` | `2026-07-26_CL-01_codex_review.md` | CHANGES_REQUESTED |
| CX-03 | `2026-07-26_CX-03_codex_handoff.md` | بانتظار Claude | HANDOFF |
| CX-02A | `2026-07-26_CX-02A_codex_handoff.md` | بانتظار Claude | HANDOFF |
| CX-02B | `2026-07-26_CX-02B_codex_handoff.md` | بانتظار Claude بعد CL-01R | HANDOFF |
