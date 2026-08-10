"""hub_online_bookings: bundle_id/children + quote snapshot + public safety fields

Revision ID: b1c2d3e4f5a6
Revises: a4b5c6d7e8f9
Create Date: 2026-08-10

OPS-DATA-02 §7.3: a public online room-booking request must persist a quote
snapshot (nightly_rate, nights, subtotal, vat, service, total, currency,
quoted_at, version) so confirmation later charges exactly what the guest was
quoted, not a live re-price ("quote drift" protection). idempotency_key_hash/
requester_hash/public_reference mirror hub_online_bookings' sibling table
contact_forms exactly.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hub_online_bookings", sa.Column(
        "bundle_id", sa.Integer(), sa.ForeignKey("room_bundles.id", ondelete="SET NULL"), nullable=True,
    ))
    op.add_column("hub_online_bookings", sa.Column(
        "children", sa.Integer(), nullable=False, server_default="0",
    ))
    op.add_column("hub_online_bookings", sa.Column("quoted_nightly_rate", sa.Numeric(10, 2), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("quoted_nights", sa.Integer(), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("quoted_subtotal", sa.Numeric(10, 2), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("quoted_vat_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("quoted_service_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("quoted_total", sa.Numeric(10, 2), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("quoted_currency", sa.String(5), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("quoted_at", sa.DateTime(), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("quote_version", sa.String(40), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("public_reference", sa.String(48), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("idempotency_key_hash", sa.String(64), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("payload_hash", sa.String(64), nullable=True))
    op.add_column("hub_online_bookings", sa.Column("requester_hash", sa.String(64), nullable=True))

    op.create_index(
        "ix_hub_online_bookings_public_reference", "hub_online_bookings", ["public_reference"], unique=True,
    )
    op.create_index(
        "ix_hub_online_bookings_requester_hash", "hub_online_bookings", ["requester_hash"],
    )
    op.create_index(
        "uq_hub_online_bookings_branch_idempotency",
        "hub_online_bookings",
        ["branch_id", "idempotency_key_hash"],
        unique=True,
        postgresql_where=sa.text("idempotency_key_hash IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_hub_online_bookings_branch_idempotency", table_name="hub_online_bookings")
    op.drop_index("ix_hub_online_bookings_requester_hash", table_name="hub_online_bookings")
    op.drop_index("ix_hub_online_bookings_public_reference", table_name="hub_online_bookings")
    op.drop_column("hub_online_bookings", "requester_hash")
    op.drop_column("hub_online_bookings", "idempotency_key_hash")
    op.drop_column("hub_online_bookings", "public_reference")
    op.drop_column("hub_online_bookings", "quote_version")
    op.drop_column("hub_online_bookings", "quoted_at")
    op.drop_column("hub_online_bookings", "quoted_currency")
    op.drop_column("hub_online_bookings", "quoted_total")
    op.drop_column("hub_online_bookings", "quoted_service_amount")
    op.drop_column("hub_online_bookings", "quoted_vat_amount")
    op.drop_column("hub_online_bookings", "quoted_subtotal")
    op.drop_column("hub_online_bookings", "quoted_nights")
    op.drop_column("hub_online_bookings", "quoted_nightly_rate")
    op.drop_column("hub_online_bookings", "children")
    op.drop_column("hub_online_bookings", "bundle_id")
