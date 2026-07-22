"""Gate 8 guest sessions, safe public references, and service queue

Revision ID: 8c12d9e4f6a1
Revises: 5fed6e302861
Create Date: 2026-07-22

This is a forward-only hardening migration.  It preserves all Gate 8 Batch
A/B rows and adds database-level concurrency guards rather than editing the
already-applied service-location-token migration.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c12d9e4f6a1"
down_revision: Union[str, None] = "5fed6e302861"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guest_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_reference", sa.String(length=48), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("service_location_token_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_location_token_id"], ["service_location_tokens.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guest_sessions_public_reference", "guest_sessions", ["public_reference"], unique=True)
    op.create_index("ix_guest_sessions_token_hash", "guest_sessions", ["token_hash"], unique=True)
    op.create_index("ix_guest_sessions_service_location_token_id", "guest_sessions", ["service_location_token_id"])
    op.create_index("ix_guest_sessions_expires_at", "guest_sessions", ["expires_at"])

    # Existing data may have more than one active token due to the old
    # deactivate-then-insert race. Keep the newest active row for each
    # physical location before installing the invariant.
    op.execute(sa.text("""
        UPDATE service_location_tokens
        SET is_active = false
        WHERE id IN (
          SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                     PARTITION BY branch_id, location_type, location_id
                     ORDER BY created_at DESC, id DESC
                   ) AS rn
            FROM service_location_tokens
            WHERE is_active = true
          ) ranked
          WHERE ranked.rn > 1
        )
    """))
    op.create_index(
        "uq_service_location_tokens_active_location",
        "service_location_tokens",
        ["branch_id", "location_type", "location_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active = 1"),
    )

    with op.batch_alter_table("guest_alerts") as batch:
        batch.add_column(sa.Column("public_reference", sa.String(length=48), nullable=True))
        batch.add_column(sa.Column("guest_session_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("outlet_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("order_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("idempotency_key", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("assigned_to", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("acknowledged_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("arrived_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key(
            "fk_guest_alert_session", "guest_sessions", ["guest_session_id"], ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_guest_alert_outlet", "dining_outlets", ["outlet_id"], ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_guest_alert_order", "dining_orders", ["order_id"], ["id"],
            ondelete="SET NULL",
        )

    op.create_index("ix_guest_alerts_public_reference", "guest_alerts", ["public_reference"], unique=True)
    op.create_index("ix_guest_alerts_guest_session_id", "guest_alerts", ["guest_session_id"])
    op.create_index("ix_guest_alerts_outlet_id", "guest_alerts", ["outlet_id"])
    op.create_index("ix_guest_alerts_order_id", "guest_alerts", ["order_id"])
    op.create_index("ix_guest_alerts_assigned_to", "guest_alerts", ["assigned_to"])

    # Preserve history while collapsing any legacy duplicate active queue
    # rows that would violate the new invariant.
    op.execute(sa.text("""
        UPDATE guest_alerts
        SET status = 'expired'
        WHERE id IN (
          SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                     PARTITION BY branch_id, context_type, context_id, alert_type
                     ORDER BY created_at DESC, id DESC
                   ) AS rn
            FROM guest_alerts
            WHERE status IN ('open', 'acknowledged', 'arrived')
          ) ranked
          WHERE ranked.rn > 1
        )
    """))
    op.create_index(
        "uq_guest_alert_active_location_type", "guest_alerts",
        ["branch_id", "context_type", "context_id", "alert_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('open','acknowledged','arrived')"),
        sqlite_where=sa.text("status IN ('open','acknowledged','arrived')"),
    )
    op.create_index(
        "uq_guest_alert_session_idempotency", "guest_alerts",
        ["guest_session_id", "idempotency_key"], unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )

    with op.batch_alter_table("dining_orders") as batch:
        batch.add_column(sa.Column("guest_session_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("guest_public_reference", sa.String(length=48), nullable=True))
        batch.create_foreign_key(
            "fk_dining_order_guest_session", "guest_sessions",
            ["guest_session_id"], ["id"], ondelete="SET NULL",
        )
    op.create_index("ix_dining_orders_guest_session_id", "dining_orders", ["guest_session_id"])
    op.create_index(
        "ix_dining_orders_guest_public_reference", "dining_orders",
        ["guest_public_reference"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_dining_orders_guest_public_reference", table_name="dining_orders")
    op.drop_index("ix_dining_orders_guest_session_id", table_name="dining_orders")
    with op.batch_alter_table("dining_orders") as batch:
        batch.drop_constraint("fk_dining_order_guest_session", type_="foreignkey")
        batch.drop_column("guest_public_reference")
        batch.drop_column("guest_session_id")

    op.drop_index("uq_guest_alert_session_idempotency", table_name="guest_alerts")
    op.drop_index("uq_guest_alert_active_location_type", table_name="guest_alerts")
    op.drop_index("ix_guest_alerts_assigned_to", table_name="guest_alerts")
    op.drop_index("ix_guest_alerts_order_id", table_name="guest_alerts")
    op.drop_index("ix_guest_alerts_outlet_id", table_name="guest_alerts")
    op.drop_index("ix_guest_alerts_guest_session_id", table_name="guest_alerts")
    op.drop_index("ix_guest_alerts_public_reference", table_name="guest_alerts")
    with op.batch_alter_table("guest_alerts") as batch:
        batch.drop_constraint("fk_guest_alert_order", type_="foreignkey")
        batch.drop_constraint("fk_guest_alert_outlet", type_="foreignkey")
        batch.drop_constraint("fk_guest_alert_session", type_="foreignkey")
        batch.drop_column("arrived_at")
        batch.drop_column("acknowledged_at")
        batch.drop_column("assigned_to")
        batch.drop_column("idempotency_key")
        batch.drop_column("order_id")
        batch.drop_column("outlet_id")
        batch.drop_column("guest_session_id")
        batch.drop_column("public_reference")

    op.drop_index("uq_service_location_tokens_active_location", table_name="service_location_tokens")
    op.drop_index("ix_guest_sessions_expires_at", table_name="guest_sessions")
    op.drop_index("ix_guest_sessions_service_location_token_id", table_name="guest_sessions")
    op.drop_index("ix_guest_sessions_token_hash", table_name="guest_sessions")
    op.drop_index("ix_guest_sessions_public_reference", table_name="guest_sessions")
    op.drop_table("guest_sessions")
