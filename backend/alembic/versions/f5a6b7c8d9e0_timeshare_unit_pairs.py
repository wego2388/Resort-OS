"""timeshare_unit_pairs + TimeshareVisit.paired_unit_id/entitlement_visit

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-08-10

OPS-DATA-02 §8 نقطة 11: عقود سعة 6 (Family Compound) لازم تاخد شاليه+استوديو
مقترنين معًا لزيارة استحقاق واحدة، مش وحدة واحدة عادية. TimeshareUnitPair
زوج معتمد (نفس مفهوم pms.RoomBundle، نسخة منفصلة عمدًا لأن TimeshareUnit
مخزون منفصل تمامًا عن pms.Room). paired_unit_id على TimeshareVisit بيسجّل
الوحدة التانية الفعلية المستخدَمة، entitlement_visit بيوثّق صراحةً إن مفيش
رسم ليلة جديد على الزيارة دي.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "timeshare_unit_pairs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chalet_unit_id", sa.Integer(), sa.ForeignKey("timeshare_units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("studio_unit_id", sa.Integer(), sa.ForeignKey("timeshare_units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("chalet_unit_id", name="uq_timeshare_unit_pair_chalet"),
        sa.UniqueConstraint("studio_unit_id", name="uq_timeshare_unit_pair_studio"),
    )

    op.add_column(
        "timeshare_visits",
        sa.Column("paired_unit_id", sa.Integer(), sa.ForeignKey("timeshare_units.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "timeshare_visits",
        sa.Column("entitlement_visit", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("timeshare_visits", "entitlement_visit")
    op.drop_column("timeshare_visits", "paired_unit_id")
    op.drop_table("timeshare_unit_pairs")
