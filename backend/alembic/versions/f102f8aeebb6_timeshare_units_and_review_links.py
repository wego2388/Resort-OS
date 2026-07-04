"""timeshare_units_and_review_links

Revision ID: f102f8aeebb6
Revises: ef29bb120188
Create Date: 2026-07-04 18:40:11.176483

يضيف:
- جدول timeshare_units (وحدات تايم شير فعلية — شاليهات/شقق منفصلة تمامًا عن
  غرف الفندق العادية pms.rooms، قرار معماري متعمد 2026-07-04).
- timeshare_contracts.unit_id — وحدة مخصَّصة دائمًا (nullable = عائم).
- timeshare_visits.unit_id — الوحدة الفعلية المخصَّصة لكل زيارة تحديدًا.
- guest_reviews.timeshare_visit_id — تقييم ضيف ممكن يُربط بزيارة تايم شير
  بدل حجز فندقي (الاثنين nullable ومستقلان عن بعض).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f102f8aeebb6'
down_revision: Union[str, None] = 'ef29bb120188'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "timeshare_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_number", sa.String(length=20), nullable=False),
        sa.Column("unit_type", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="available"),
        sa.Column("notes", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("branch_id", "unit_number", name="uq_timeshare_unit_branch_number"),
    )

    op.add_column("timeshare_contracts", sa.Column("unit_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_timeshare_contracts_unit_id", "timeshare_contracts", "timeshare_units",
        ["unit_id"], ["id"], ondelete="SET NULL",
    )

    op.add_column("timeshare_visits", sa.Column("unit_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_timeshare_visits_unit_id", "timeshare_visits", "timeshare_units",
        ["unit_id"], ["id"], ondelete="SET NULL",
    )

    op.add_column("guest_reviews", sa.Column("timeshare_visit_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_guest_reviews_timeshare_visit_id", "guest_reviews", "timeshare_visits",
        ["timeshare_visit_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_guest_reviews_timeshare_visit_id", "guest_reviews", type_="foreignkey")
    op.drop_column("guest_reviews", "timeshare_visit_id")

    op.drop_constraint("fk_timeshare_visits_unit_id", "timeshare_visits", type_="foreignkey")
    op.drop_column("timeshare_visits", "unit_id")

    op.drop_constraint("fk_timeshare_contracts_unit_id", "timeshare_contracts", type_="foreignkey")
    op.drop_column("timeshare_contracts", "unit_id")

    op.drop_table("timeshare_units")
