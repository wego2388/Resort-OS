"""
alembic/env.py
Auto-detects all models via import — single migration chain
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Load app settings ─────────────────────────────────────────────────────────
from app.core.config import settings
from app.core.database import Base

# ── Import ALL models so Alembic can detect them ─────────────────────────────
# ⚠️ app.core.kernel.models.user لازم يتحمّل هنا كمان — من غيره أي FK بيشاور
# على "users" (audit_logs.user_id وغيره) بيفشل بـ NoReferencedTableError وقت
# --autogenerate (sorted_tables بيحاول يرتّب كل الجداول طوبولوجياً، مش بس
# اللي اتغيّرت). كان ده بايق كامل قدرة autogenerate من الاشتغال أصلاً.
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

# ⚠️ DINING_CUTOVER_PLAN.md Batch 6 (2026-07-13): restaurant/cafe.models
# اتشالوا من هنا لأن الموديولين نفسهم اتحذفوا بالكامل من المشروع (dining هو
# مصدر الحقيقة الوحيد للـ Outlet/orders دلوقتي). جداولهم (menu_items,
# orders, cafe_items, cafe_orders, ...) لسه موجودة فعليًا في Postgres عمدًا
# (أرشيف احتياطي، راجع CLAUDE.md §18) — بس مش في SQLAlchemy metadata بقى.
# **لو شغّلت `alembic revision --autogenerate` بعد كده**، Alembic هيقترح
# DROP TABLE لكل جدول restaurant/cafe القديم (لأنه شايفهم في الداتابيز
# ومش شايفهم في الـ models) — **لازم تمسح أسطر الـ DROP دي يدويًا** من أي
# migration جديدة قبل ما تطبّقها؛ الجداول دي المفروض تفضل زي ما هي للأبد
# كنسخة احتياطية، مش تتحذف أبدًا عبر أي migration.

# ── Alembic Config ────────────────────────────────────────────────────────────
config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
