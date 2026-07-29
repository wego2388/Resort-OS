# سير العمل الحالي — El Kheima

هذا الدليل يكمّل `AGENTS.md` و`CLAUDE.md` ولا يستبدلهما. مصدر فهرسة
التوثيق هو `docs/README.md`.

## الأدوار

| الدور | المسؤولية |
|---|---|
| Mohamed | قرارات المنتج والبيانات الحقيقية وGo/No-Go |
| Codex | قائد التنفيذ، المراجع النهائي، تكامل الكود، وإدارة VPS ضمن التفويض |
| أي مساهم آخر | مهمة محددة فقط، ولا يغيّر حالة أو نشرًا دون تسليم ومراجعة Codex |

لا يوجد حاليًا بروتوكول تنفيذ مزدوج أو ملكية ملفات متوازية. البروتوكول القديم
مؤرشف ولا يُستخدم.

## دورة التغيير

1. اقرأ المصادر الحالية بالترتيب في `docs/README.md`.
2. افحص Git والبيئة قراءةً فقط.
3. حدّد outcome وحدود المهمة ومعايير القبول والتراجع.
4. نفّذ أصغر حزمة متماسكة.
5. شغّل targeted checks ثم full affected gates.
6. راجع diff أمنيًا ووظيفيًا وماليًا وتشغيليًا.
7. حدّث `wagdy.md` أولًا عند تغير القرار أو الحالة.
8. حدّث status/plan/board، وأنشئ handoff عند إغلاق الحزمة.
9. commit محلي بعد اكتمال المراجعة؛ push والنشر خطوتان منفصلتان.
10. production change يحتاج backup/rollback/health/evidence.

## قواعد الإنتاج

- لا تغيّر نظامًا حيًا أثناء discovery.
- لا تستخدم Git لتنظيف production worktree غير معروف.
- لا تعرض أسرارًا أو `docker inspect .Config.Env`.
- لا تشغّل migrations أو seed أو scripts domain ضمن فحص الحالة.
- اربط كل release بـcommit وimage digest ووقت build.
- سجّل ما تغير وما لم يتغير ونتيجة rollback/health.
- أي تغيير عالي الأثر يبدأ بنقطة تراجع قابلة للاختبار.

## بوابة الجودة

- acceptance criteria متحققة.
- الصلاحيات وعزل الفرع واختبارات الأدوار مغطاة.
- invariants المالية والتزامن مغطاة عند تغير المعاملات.
- frontend tests/typecheck/build ناجحة عند تغير الواجهة.
- backend targeted/full suites ناجحة حسب النطاق.
- Alembic single-head وتأثير upgrade/downgrade واضح.
- `git diff --check` ناجح، ولا secrets أو ملفات مستخدم غير مقصودة.
- التوثيق الحالي لا يحتوي أمرًا متعارضًا.
- لا deploy قبل rollback point وGo/No-Go المناسب.

## الملفات النشطة

- `TASK_BRIEF_TEMPLATE.md` — عقد مهمة محددة.
- `REVIEW_TEMPLATE.md` — صيغة مراجعة بالأدلة.
- `PROMPT_LIBRARY.md` — مساعد صياغة؛ لا يتقدم على الخطة.
- `EL_KHEIMA_EXECUTION_BOARD.md` — المهمة الحالية الوحيدة.
- `handoffs/` — سجل الحزم المنتهية.

الملفات القديمة نُقلت إلى `docs/archive/2026-07-execution/` وهي غير قابلة
للتنفيذ.
