"""Fix missing server_default now() on created_at/updated_at for 5 finance tables

The original migration (d1e3f920_finance_check_cost_center.py) created
cost_centers/exchange_rates/checks/check_movements/revenue_audit_logs with
plain `nullable=False` timestamp columns but no `server_default` — the ORM
models (via wego_core's TimestampMixin) declare `server_default=func.now()`,
so SQLite-backed tests (which build tables straight from the models via
`Base.metadata.create_all()`) never noticed, but every real Postgres insert
that doesn't explicitly set created_at/updated_at fails with a NOT NULL
violation. Discovered while wiring the new Cost Center report (2026-07-01).

Revision ID: fix_ts_defaults
Revises: 34953a3c2847
Create Date: 2026-07-01
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "fix_ts_defaults"
down_revision: Union[str, None] = "34953a3c2847"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ["cost_centers", "exchange_rates", "checks", "check_movements", "revenue_audit_logs"]


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "created_at", server_default=sa.text("now()"))
        op.alter_column(table, "updated_at", server_default=sa.text("now()"))


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "created_at", server_default=None)
        op.alter_column(table, "updated_at", server_default=None)
