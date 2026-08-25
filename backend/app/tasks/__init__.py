"""app/tasks/__init__.py

يستورد كل ملفات الـ tasks تلقائياً عند استيراد الـ package — عشان أي @celery_app.task
جديد يتسجل من غير ما حد يحتاج يضيف import يدوي في celery_app.py (كان ده مصدر باج
كلاسيكي: task جديد في beat_schedule بينادي عليه الـ worker بدون ما يكون متسجل).

⚠️ 2026-08-24/25، باج إنتاج حقيقي (REL-20 follow-up): `timeshare-mark-overdue`
(أول task في جدول اليوم بيلمس FK حقيقي — `timeshare_contracts.cancelled_by`)
كان بيفشل بـ`NoReferencedTableError` باستمرار على الإنتاج، رغم إن نفس
الاستعلام بالظبط اشتغل عادي في كل الـ backend tests. السبب: كل استيرادات
tasks/*.py هنا لموديولات الأعمال (crud/services/models) مُؤجَّلة عمدًا جوه
function bodies (نمط متعمد لتخفيف startup) — عملية Celery worker الحقيقية
عمرها ما بتستورد `app.main` (اللي بيحمّل كل الموديولات عبر الـrouters)، فأي
موديل عنده ForeignKey حقيقي (مش عمود int عادي) على جدول تاني ممكن يفضل غير
مُسجَّل في Base.metadata لحد أول مرة أي task حقيقي يلمسه فعليًا — وده حصل
هنا مع `users` (تجربة أولى)، وبعد إصلاحها ظهرت بالظبط نفس المشكلة تاني مع
`branches` (اتأكد حي على الإنتاج، مش افتراض). **نفس الحل بالظبط الموثّق في
alembic/env.py لنفس الفخ** (راجع §13 بند ❹-ب في CLAUDE.md) — استيراد صريح
لكل app.modules.<x>.models، يضمن كل موديل مُسجَّل قبل أي task يشتغل خالص.
"""
from __future__ import annotations

import importlib
import pkgutil

# راجع الشرح فوق — نفس القايمة بالظبط الموجودة في alembic/env.py (بما فيها
# app.core.kernel.models.user، اللي مش بيتحمّل تلقائيًا عبر app.modules.core.models).
import app.core.kernel.models.user    # noqa: F401
import app.modules.core.models        # noqa: F401
import app.modules.finance.models     # noqa: F401
import app.modules.hr.models          # noqa: F401
import app.modules.pms.models         # noqa: F401
import app.modules.beach.models       # noqa: F401
import app.modules.inventory.models    # noqa: F401
import app.modules.timeshare.models    # noqa: F401
import app.modules.leasing.models      # noqa: F401
import app.modules.crm.models          # noqa: F401
import app.modules.maintenance.models  # noqa: F401
import app.modules.hub.models          # noqa: F401
import app.modules.analytics.models   # noqa: F401
import app.modules.dining.models      # noqa: F401
import app.modules.chat.models        # noqa: F401
import app.modules.owner.models       # noqa: F401
import app.modules.credit.models      # noqa: F401

for _module_info in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module_info.name}")
