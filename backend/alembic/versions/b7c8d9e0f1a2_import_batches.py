"""import_batches table (HIST-01 manifest/rollback tracking)

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-08-10

OPS-DATA-02 §9.1/§9.3: مصدر حقيقة app.operational_history_seed — منع
تشغيل نفس (فرع+نسخة+فترة) مرتين حتى بعد crash، ومانifest كامل
(counts/totals) للتحقق والـrollback.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a2"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_version", sa.String(50), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("counts", sa.Text(), nullable=True),
        sa.Column("totals", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("branch_id", "dataset_version", "period",
                             name="uq_import_batch_branch_version_period"),
    )


def downgrade() -> None:
    op.drop_table("import_batches")
