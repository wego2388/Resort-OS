"""Fix missing server_default/NOT NULL on created_at/updated_at for 6 PMS/analytics tables

Same root cause as fix_timestamp_defaults_5tables.py (2026-07-01) and
fix_timestamp_defaults_crm_hub.py (2026-07-03): the ORM models (via
TimestampMixin) declare `created_at`/`updated_at` as
`nullable=False, server_default=func.now()`, but the hand-written migration
that created these 6 tables (c9f1a852_new_models.py) declared them plain
`nullable=True` with no `server_default` at all — worse than the previous two
occurrences, which only forgot the default (columns were still NOT NULL).
SQLite-backed tests never notice (Base.metadata.create_all() builds tables
straight from the model definitions, defaults included), but real Postgres
inserts that don't explicitly set created_at/updated_at silently get NULL
instead of "now()".

Discovered 2026-07-03 (QA pass) via a live 500 on GET /pms/housekeeping/tasks:
`HousekeepingTaskRead.created_at` (a required datetime field) failed pydantic
validation because one real row in housekeeping_tasks had created_at=NULL. A
full information_schema audit across the whole database (same technique used
in fix_timestamp_defaults_crm_hub.py) found exactly 6 affected tables, all
from the same original migration: housekeeping_tasks, rate_plans, daily_stats,
guest_reviews, review_categories, utility_readings — no other tables in the
database currently have this drift.

This migration also backfills any existing NULL rows before enforcing NOT
NULL (the previous two fixes for this bug class didn't need to, since their
columns were already NOT NULL — these 6 tables also had the nullable=True
half of the same original mistake).

Revision ID: fix_ts_pms_analytics
Revises: fix_ts_crm_hub
Create Date: 2026-07-03
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "fix_ts_pms_analytics"
down_revision: Union[str, None] = "fix_ts_crm_hub"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    "housekeeping_tasks", "rate_plans", "daily_stats",
    "guest_reviews", "review_categories", "utility_readings",
]


def upgrade() -> None:
    for table in TABLES:
        for col in ("created_at", "updated_at"):
            op.execute(f"UPDATE {table} SET {col} = now() WHERE {col} IS NULL")
        op.alter_column(table, "created_at", server_default=sa.text("now()"), nullable=False)
        op.alter_column(table, "updated_at", server_default=sa.text("now()"), nullable=False)


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "created_at", server_default=None, nullable=True)
        op.alter_column(table, "updated_at", server_default=None, nullable=True)
