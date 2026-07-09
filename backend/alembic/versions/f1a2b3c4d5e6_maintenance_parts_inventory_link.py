"""Link WorkOrderPart to inventory products — deduct stock on part consumption

Revision ID: f1a2b3c4d5e6
Revises: e7f3a2b1c904
Create Date: 2026-07-09

المشكلة: WorkOrderPart عنده part_name نصي بس — مفيش ربط بـ inventory.products.
لما الفني يصرف قطعة غيار من المخزن، الكمية ما بتتخصمش تلقائياً.
الحل: إضافة product_id (FK اختياري) — لو موجود بيخصم من المخزن عند إضافة القطعة.
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa


revision: str = "d9e8f7a6b5c4"
down_revision: str = "e7f3a2b1c904"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # product_id اختياري — لو None معناه قطعة خارجية مش موجودة في المخزن
    op.add_column(
        "work_order_parts",
        sa.Column(
            "product_id",
            sa.Integer,
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_work_order_parts_product_id", "work_order_parts", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_work_order_parts_product_id", "work_order_parts")
    op.drop_column("work_order_parts", "product_id")
