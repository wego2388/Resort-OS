"""add dining order guest reviews

Revision ID: d2e4f6a8c0b1
Revises: 0ccdcfb7c5c9
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa

revision = "d2e4f6a8c0b1"
down_revision = "0ccdcfb7c5c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guest_reviews",
        sa.Column("dining_order_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "guest_reviews",
        sa.Column("guest_session_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_guest_reviews_dining_order_id",
        "guest_reviews",
        "dining_orders",
        ["dining_order_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_guest_review_dining_order",
        "guest_reviews",
        ["dining_order_id"],
        unique=True,
        postgresql_where=sa.text("dining_order_id IS NOT NULL"),
    )
    op.create_foreign_key(
        "fk_guest_reviews_guest_session_id",
        "guest_reviews",
        "guest_sessions",
        ["guest_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_guest_review_guest_session",
        "guest_reviews",
        ["guest_session_id"],
        unique=True,
        postgresql_where=sa.text("guest_session_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_guest_review_guest_session", table_name="guest_reviews")
    op.drop_constraint(
        "fk_guest_reviews_guest_session_id",
        "guest_reviews",
        type_="foreignkey",
    )
    op.drop_index("uq_guest_review_dining_order", table_name="guest_reviews")
    op.drop_constraint(
        "fk_guest_reviews_dining_order_id",
        "guest_reviews",
        type_="foreignkey",
    )
    op.drop_column("guest_reviews", "guest_session_id")
    op.drop_column("guest_reviews", "dining_order_id")
