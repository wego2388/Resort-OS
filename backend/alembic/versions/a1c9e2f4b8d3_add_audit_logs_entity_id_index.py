"""add missing index on audit_logs.entity_id

Revision ID: a1c9e2f4b8d3
Revises: f102f8aeebb6
Create Date: 2026-07-05 06:30:00.000000

GET /api/v1/audit-logs (list_audit_logs) can filter by entity_id, and this
table is append-only (audit logs are never pruned) — every other filter
column on this table (user_id, branch_id, action, entity_type) already had
an index in the live database (added by an earlier migration but never
reflected back into app/modules/core/models.py's `index=True` flags — that
drift is fixed alongside this migration). entity_id itself was the one
genuinely missing index, meaning any entity_id-filtered audit query was a
full table scan.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = 'a1c9e2f4b8d3'
down_revision: Union[str, None] = 'f102f8aeebb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f('ix_audit_logs_entity_id'), 'audit_logs', ['entity_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_logs_entity_id'), table_name='audit_logs')
