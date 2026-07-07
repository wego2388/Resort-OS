"""guest_alerts

Revision ID: 55029698cdf1
Revises: a4d7c2e8f910
Create Date: 2026-07-07

Adds the guest_alerts table — a generic, guest-initiated staff-alert
channel ("call waiter" / "request bill") triggered from the unauthenticated
QR ordering flow, delivered live to staff over WebSocket. See
app/modules/core/models.py::GuestAlert for the full design rationale
(context_type/context_id is deliberately not a real ForeignKey — a single
alert table must be able to reference any context: a restaurant table, a
cafe table, a PMS room, a beach location, etc.).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "55029698cdf1"
down_revision: Union[str, None] = "a4d7c2e8f910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guest_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("context_type", sa.String(length=30), nullable=False),
        sa.Column("context_id", sa.Integer(), nullable=False),
        sa.Column("alert_type", sa.String(length=30), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_guest_alerts_branch_id"), "guest_alerts", ["branch_id"], unique=False)
    op.create_index(op.f("ix_guest_alerts_status"), "guest_alerts", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_guest_alerts_status"), table_name="guest_alerts")
    op.drop_index(op.f("ix_guest_alerts_branch_id"), table_name="guest_alerts")
    op.drop_table("guest_alerts")
