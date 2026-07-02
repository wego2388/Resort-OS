"""eta_invoices_table

Revision ID: 12f21e50c5f0
Revises: 347cbfa7a11d
Create Date: 2026-07-01

Tracks Egyptian Tax Authority (ETA) e-invoice submissions: the document we
built, ETA's response, and status — for audit + retry.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "12f21e50c5f0"
down_revision: str | None = "347cbfa7a11d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eta_invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("folio_id", sa.Integer(), nullable=True),
        sa.Column("internal_id", sa.String(length=50), nullable=False),
        sa.Column("submission_uuid", sa.String(length=100), nullable=True),
        sa.Column("long_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("document_json", sa.Text(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folio_id"], ["folios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("internal_id"),
    )


def downgrade() -> None:
    op.drop_table("eta_invoices")
