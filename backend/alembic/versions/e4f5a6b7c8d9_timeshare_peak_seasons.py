"""timeshare_peak_seasons table

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-08-10

OPS-DATA-02 §8 نقطة 5: مواسم ذروة حقيقية في الـDB (كانت غير موجودة خالص
قبل كده — الذروة مش محددة في مكان غير كود ثابت). peak_kind يفرّق العيد
الرسمي عن الموسم العادي (صيف) عشان قاعدة عدم تتابع الأعياد تتحقق بس على
النوع الصح. created_by nullable لأن FK بتاعها ondelete=SET NULL (نقطة 4).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "timeshare_peak_seasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_ar", sa.String(100), nullable=True),
        sa.Column("peak_kind", sa.String(20), nullable=False, server_default="regular"),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_timeshare_peak_seasons_season_year", "timeshare_peak_seasons", ["season_year"])
    op.create_index("ix_timeshare_peak_seasons_start_date", "timeshare_peak_seasons", ["start_date"])


def downgrade() -> None:
    op.drop_index("ix_timeshare_peak_seasons_start_date", table_name="timeshare_peak_seasons")
    op.drop_index("ix_timeshare_peak_seasons_season_year", table_name="timeshare_peak_seasons")
    op.drop_table("timeshare_peak_seasons")
