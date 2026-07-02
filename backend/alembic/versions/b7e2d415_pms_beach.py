"""pms_beach_tables

Revision ID: b7e2d415
Revises: a3f8c291
Create Date: 2026-06-30 09:30:00

Tables: room_types, rooms, bookings, booking_rooms, night_audit_logs,
        beach_inventory, beach_transactions, b2b_contracts,
        b2b_contract_days, beach_reservations
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision      = "b7e2d415"
down_revision = "a3f8c291"
branch_labels = None
depends_on    = None


def upgrade() -> None:

    # ── PMS ───────────────────────────────────────────────────────────
    op.create_table(
        "room_types",
        sa.Column("id",            sa.Integer(),      nullable=False),
        sa.Column("branch_id",     sa.Integer(),      nullable=False),
        sa.Column("name",          sa.String(100),    nullable=False),
        sa.Column("name_ar",       sa.String(100),    nullable=True),
        sa.Column("base_rate",     sa.Numeric(10, 2), nullable=False),
        sa.Column("max_occupancy", sa.Integer(),      nullable=False, server_default="2"),
        sa.Column("amenities",     sa.Text(),         nullable=True),
        sa.Column("is_active",     sa.Boolean(),      nullable=False, server_default="true"),
        sa.Column("created_at",    sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",    sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rooms",
        sa.Column("id",           sa.Integer(),  nullable=False),
        sa.Column("branch_id",    sa.Integer(),  nullable=False),
        sa.Column("room_type_id", sa.Integer(),  nullable=False),
        sa.Column("name",         sa.String(20), nullable=False),
        sa.Column("floor",        sa.Integer(),  nullable=False, server_default="1"),
        sa.Column("status",       sa.String(30), nullable=False, server_default="available"),
        sa.Column("notes",        sa.String(300),nullable=True),
        sa.Column("created_at",   sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",   sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"],    ["branches.id"],   ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_type_id"], ["room_types.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "name", name="uq_room_branch_name"),
    )
    op.create_index("ix_rooms_branch_status", "rooms", ["branch_id", "status"])

    op.create_table(
        "bookings",
        sa.Column("id",               sa.Integer(),      nullable=False),
        sa.Column("branch_id",        sa.Integer(),      nullable=False),
        sa.Column("booking_number",   sa.String(30),     nullable=False),
        sa.Column("guest_name",       sa.String(200),    nullable=False),
        sa.Column("guest_phone",      sa.String(20),     nullable=True),
        sa.Column("guest_email",      sa.String(100),    nullable=True),
        sa.Column("guest_national_id",sa.String(20),     nullable=True),
        sa.Column("check_in",         sa.Date(),         nullable=False),
        sa.Column("check_out",        sa.Date(),         nullable=False),
        sa.Column("adults",           sa.Integer(),      nullable=False, server_default="1"),
        sa.Column("children",         sa.Integer(),      nullable=False, server_default="0"),
        sa.Column("status",           sa.String(30),     nullable=False, server_default="confirmed"),
        sa.Column("source",           sa.String(30),     nullable=False, server_default="direct"),
        sa.Column("folio_id",         sa.Integer(),      nullable=True),
        sa.Column("total_rate",       sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notes",            sa.Text(),         nullable=True),
        sa.Column("cancelled_at",     sa.DateTime(),     nullable=True),
        sa.Column("cancelled_by",     sa.Integer(),      nullable=True),
        sa.Column("created_at",       sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",       sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folio_id"],  ["folios.id"],   ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_number"),
    )
    op.create_index("ix_bookings_branch_status",   "bookings", ["branch_id", "status"])
    op.create_index("ix_bookings_branch_check_in", "bookings", ["branch_id", "check_in"])

    op.create_table(
        "booking_rooms",
        sa.Column("id",         sa.Integer(),      nullable=False),
        sa.Column("booking_id", sa.Integer(),      nullable=False),
        sa.Column("room_id",    sa.Integer(),      nullable=False),
        sa.Column("daily_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("nights",     sa.Integer(),      nullable=False),
        sa.Column("total",      sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"],    ["rooms.id"],    ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", "room_id", name="uq_booking_room"),
    )

    op.create_table(
        "night_audit_logs",
        sa.Column("id",              sa.Integer(),      nullable=False),
        sa.Column("branch_id",       sa.Integer(),      nullable=False),
        sa.Column("audit_date",      sa.Date(),         nullable=False),
        sa.Column("occupied_rooms",  sa.Integer(),      nullable=False, server_default="0"),
        sa.Column("total_rooms",     sa.Integer(),      nullable=False, server_default="0"),
        sa.Column("occupancy_pct",   sa.Numeric(5, 2),  nullable=False, server_default="0"),
        sa.Column("room_revenue",    sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("no_shows",        sa.Integer(),      nullable=False, server_default="0"),
        sa.Column("checkouts_today", sa.Integer(),      nullable=False, server_default="0"),
        sa.Column("checkins_today",  sa.Integer(),      nullable=False, server_default="0"),
        sa.Column("status",          sa.String(20),     nullable=False, server_default="pending"),
        sa.Column("completed_at",    sa.DateTime(),     nullable=True),
        sa.Column("gm_notified",     sa.Boolean(),      nullable=False, server_default="false"),
        sa.Column("summary_json",    sa.Text(),         nullable=True),
        sa.Column("created_at",      sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "audit_date", name="uq_audit_branch_date"),
    )

    # ── Beach ─────────────────────────────────────────────────────────
    op.create_table(
        "beach_inventory",
        sa.Column("id",               sa.Integer(),     nullable=False),
        sa.Column("branch_id",        sa.Integer(),     nullable=False),
        sa.Column("inventory_date",   sa.Date(),        nullable=False),
        sa.Column("capacity_max",     sa.Integer(),     nullable=False, server_default="200"),
        sa.Column("capacity_used",    sa.Integer(),     nullable=False, server_default="0"),
        sa.Column("towels_total",     sa.Integer(),     nullable=False, server_default="200"),
        sa.Column("towels_available", sa.Integer(),     nullable=False, server_default="200"),
        sa.Column("towels_used",      sa.Integer(),     nullable=False, server_default="0"),
        sa.Column("surge_pct",        sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("created_at",       sa.DateTime(),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",       sa.DateTime(),    nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "inventory_date", name="uq_beach_inventory_date"),
    )

    op.create_table(
        "b2b_contracts",
        sa.Column("id",            sa.Integer(),      nullable=False),
        sa.Column("branch_id",     sa.Integer(),      nullable=False),
        sa.Column("hotel_name",    sa.String(200),    nullable=False),
        sa.Column("hotel_name_ar", sa.String(200),    nullable=True),
        sa.Column("contact_phone", sa.String(20),     nullable=True),
        sa.Column("daily_quota",   sa.Integer(),      nullable=False, server_default="50"),
        sa.Column("entry_price",   sa.Numeric(10, 2), nullable=False),
        sa.Column("towel_price",   sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("valid_from",    sa.Date(),         nullable=False),
        sa.Column("valid_until",   sa.Date(),         nullable=False),
        sa.Column("is_active",     sa.Boolean(),      nullable=False, server_default="true"),
        sa.Column("notes",         sa.Text(),         nullable=True),
        sa.Column("created_at",    sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",    sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "beach_transactions",
        sa.Column("id",              sa.Integer(),      nullable=False),
        sa.Column("branch_id",       sa.Integer(),      nullable=False),
        sa.Column("tx_type",         sa.String(30),     nullable=False),
        sa.Column("quantity",        sa.Integer(),      nullable=False, server_default="1"),
        sa.Column("unit_price",      sa.Numeric(10, 2), nullable=False),
        sa.Column("total_amount",    sa.Numeric(10, 2), nullable=False),
        sa.Column("vat_amount",      sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("surge_applied",   sa.Boolean(),      nullable=False, server_default="false"),
        sa.Column("tx_date",         sa.Date(),         nullable=False),
        sa.Column("cashier_id",      sa.Integer(),      nullable=True),
        sa.Column("folio_id",        sa.Integer(),      nullable=True),
        sa.Column("b2b_contract_id", sa.Integer(),      nullable=True),
        sa.Column("notes",           sa.String(300),    nullable=True),
        sa.Column("voided_at",       sa.DateTime(),     nullable=True),
        sa.Column("voided_by",       sa.Integer(),      nullable=True),
        sa.Column("created_at",      sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"],       ["branches.id"],    ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folio_id"],        ["folios.id"],      ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["b2b_contract_id"], ["b2b_contracts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_beach_tx_date", "beach_transactions", ["branch_id", "tx_date"])

    op.create_table(
        "b2b_contract_days",
        sa.Column("id",                     sa.Integer(),      nullable=False),
        sa.Column("contract_id",            sa.Integer(),      nullable=False),
        sa.Column("day",                    sa.Date(),         nullable=False),
        sa.Column("checked_in_count",       sa.Integer(),      nullable=False, server_default="0"),
        sa.Column("total_amount",           sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("notified_quota_warning", sa.Boolean(),      nullable=False, server_default="false"),
        sa.Column("created_at",             sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",             sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["contract_id"], ["b2b_contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "day", name="uq_b2b_contract_day"),
    )

    op.create_table(
        "beach_reservations",
        sa.Column("id",               sa.Integer(),      nullable=False),
        sa.Column("branch_id",        sa.Integer(),      nullable=False),
        sa.Column("guest_name",       sa.String(200),    nullable=False),
        sa.Column("guest_phone",      sa.String(20),     nullable=True),
        sa.Column("reservation_date", sa.Date(),         nullable=False),
        sa.Column("guests_count",     sa.Integer(),      nullable=False, server_default="1"),
        sa.Column("with_towel",       sa.Boolean(),      nullable=False, server_default="false"),
        sa.Column("status",           sa.String(20),     nullable=False, server_default="pending"),
        sa.Column("total_amount",     sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("tx_id",            sa.Integer(),      nullable=True),
        sa.Column("notes",            sa.String(300),    nullable=True),
        sa.Column("created_at",       sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",       sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"],          ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tx_id"],     ["beach_transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_beach_reservations_date", "beach_reservations", ["branch_id", "reservation_date"])


def downgrade() -> None:
    op.drop_table("beach_reservations")
    op.drop_table("b2b_contract_days")
    op.drop_table("beach_transactions")
    op.drop_table("b2b_contracts")
    op.drop_table("beach_inventory")
    op.drop_table("night_audit_logs")
    op.drop_table("booking_rooms")
    op.drop_table("bookings")
    op.drop_table("rooms")
    op.drop_table("room_types")
