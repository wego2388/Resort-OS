# بروتوكول التنفيذ المزدوج — Codex وClaude

هذا البروتوكول خاص بخطة إنتاج الخيمة ويكمل `README.md`. عند تعارض توزيع الأدوار العام في `README.md` مع هذه الخطة، يطبق هذا البروتوكول على حزم الخيمة فقط: **كل من Codex وClaude ينفذ حزمًا مستقلة، والآخر يراجعها.**

## الهدف المشترك

تنفيذ `docs/audits/EL_KHEIMA_FINAL_EXECUTION_PLAN_AR.md` بالكامل، بسرعة منضبطة، من دون تضارب ملفات أو خفض معايير الأمن والبيانات والجودة.

## أول 60 ثانية لأي جلسة

يقرأ الوكيل، بالترتيب:

1. `AGENTS.md` وتعليمات الوكيل الخاصة إن وجدت.
2. `docs/audits/EL_KHEIMA_FINAL_EXECUTION_PLAN_AR.md`.
3. `docs/agent-workflow/EL_KHEIMA_EXECUTION_BOARD.md`.
4. Task brief وhandoff للحزمة الحالية.
5. ثم يفحص:

```bash
git status --short --branch
git branch --show-current
git rev-parse --short HEAD
git worktree list
```

إذا وجد تعديلات غير مملوكة له أو ملفًا معلنًا كـlocked، يتوقف عن تعديل تلك الملفات ويكمل فقط في نطاق مستقل.

## حالات الحزمة

```text
BACKLOG → READY → IN_PROGRESS → HANDOFF → REVIEW
        → REMEDIATION → ACCEPTED → INTEGRATED → DONE
```

- `BLOCKED` يستخدم فقط مع سبب محدد وقرار مطلوب.
- حزمة واحدة فقط `IN_PROGRESS` لكل وكيل.
- `DONE` تعني مدمجة واختباراتها ناجحة، وليست مجرد انتهاء كتابة الكود.

## الملكية

### Claude

- الشات بوت الحالي كاملًا حتى أول handoff.
- موقع التسويق: public client وService Worker وconsent وcontact والمحتوى وSEO والاختبارات.
- لا يعدل auth/PMS/branch membership أو VPS/compose إلا بعد تسليم جديد يغيّر الملكية.

### Codex

- تكامل الخطة والبوابات.
- Backend auth/permissions/PMS والفروع.
- تطبيق الموظفين وQR/PWA.
- Production bootstrap/import.
- CI/CD وDocker وHostinger VPS وDNS/TLS والنسخ والمراقبة.
- لا يعدل ملفات الشات أو ملفات موقع التسويق المعلنة كقيد عمل Claude قبل handoff.

### الملفات المشتركة

`main.py`, `config.py`, `rate_limit.py`, `.env.example`, Alembic، public contracts، compose وNginx لا يملكها وكيلان في الوقت نفسه. اسم المالك الحالي يسجل في لوحة التنفيذ.

## نموذج Claim

قبل التعديل يضيف المنفذ إلى حالته:

```markdown
- Packet:
- Status: IN_PROGRESS
- Base SHA:
- Branch/worktree:
- Expected files:
- Shared files claimed:
- Acceptance criteria:
- Started at:
```

لا تكفي عبارة "أعمل على الباك إند". يجب تحديد الحزمة والملفات والعقد.

## عقد الواجهة قبل الكود

أي عمل يربط المستودعين أو الواجهة بالـBackend يبدأ بعقد قصير:

- route + method.
- request/response schema.
- auth/permission/branch derivation.
- validation وrate/cache rules.
- error codes.
- compatibility window.
- contract tests.

يوافق المراجع على العقد قبل أن يبني المستهلك والمنتج في وقت واحد.

## نموذج Handoff

كل تسليم يجب أن يحتوي:

```markdown
# Handoff <packet-id>

- Implementer:
- Base SHA / target SHA or uncommitted diff:
- Worktree:
- Outcome:
- Files changed:
- Shared files released:
- API/schema/migration changes:
- Commands run and exact results:
- Security/data/branch/UX checks:
- Known limitations:
- Deferred findings with owner/date:
- Reviewer should focus on:
```

لو التغيير غير committed، يراجع الوكيل الآخر في نفس worktree بوضع read-only. لو committed، يراجع SHA range صريحًا.

## المراجعة المتبادلة

- Claude ينفذ → Codex يراجع.
- Codex ينفذ → Claude يراجع.
- المراجع لا يصلح بنفسه في نفس pass.
- النتائج Critical/High توقف Gate.
- Medium إما يصلح أو يسجل باستثناء له مالك وموعد.
- Low يجمع في حزمة Low ولا يوسع الحزمة الحالية.
- المنفذ الأصلي يكتب ردًا لكل finding: fixed، deferred-approved، أو rejected-with-evidence.

## Git وWorktrees

1. لا إنشاء worktree قبل حفظ وفهم كل تعديل قائم.
2. كل حزمة مستقلة لها branch/worktree من base SHA مراجَع.
3. لا rebase/merge/push/reset/حذف worktree دون تسجيل وموافقة المالك المطلوبة.
4. لا cherry-pick لحزمة قبل نجاح review gate.
5. مسؤول التكامل يفحص بعد كل دمج:
   - conflicts.
   - Alembic heads.
   - API contract drift.
   - full affected gates.

## قواعد قاعدة البيانات

- Codex هو migration coordinator بعد انتهاء migration الشات الحالية.
- Claude يطلب schema change عبر contract؛ لا ينشئ migration موازية من base قديم.
- كل migration لها existing-data report واختبار PostgreSQL وroll-forward plan.
- لا بيانات إنتاجية أو PII في fixtures أو commits أو handoff.

## قواعد الـVPS والخدمات الخارجية

- Codex وحده ينفذ تغييرات Hostinger/VPS/DNS ضمن هذه الخطة.
- القراءة والاستكشاف يسجلان في اللوحة.
- writes الحساسة تتطلب approval وpreflight وrollback.
- Claude يراجع manifests/configs/scripts، ولا يغير الإنتاج مباشرة.
- الأسرار لا تُنسخ إلى chat أو اللوحة أو Git.

## Stop conditions

يتوقف الوكيل ويطلب قرار المالك عند:

- تضارب ملكية ملف أو عمل غير محفوظ لوكيل آخر.
- حذف/استبدال بيانات أو migration هدّام.
- تغيير DNS أو restore أو secret rotation قد يقطع خدمة قائمة.
- معلومة تجارية/مالية/قانونية غير قابلة للاستنتاج الآمن.
- فشل gate ثلاث مرات بسبب نفس blocker خارجي.

## تقرير نهاية الجلسة

لا ينهي الوكيل جلسة تنفيذ دون تحديث ملف حالته في اللوحة:

- ماذا اكتمل.
- ما لم يكتمل.
- آخر SHA وحالة worktree.
- الاختبارات.
- الملف/الحزمة الآمنة التالية.
- أي lock ما زال قائمًا.

