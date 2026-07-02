"""app/tasks/__init__.py

يستورد كل ملفات الـ tasks تلقائياً عند استيراد الـ package — عشان أي @celery_app.task
جديد يتسجل من غير ما حد يحتاج يضيف import يدوي في celery_app.py (كان ده مصدر باج
كلاسيكي: task جديد في beat_schedule بينادي عليه الـ worker بدون ما يكون متسجل).
"""
from __future__ import annotations

import importlib
import pkgutil

for _module_info in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module_info.name}")
