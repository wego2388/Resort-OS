"""initial_core_tables

Revision ID: 47f5f348
Revises:
Create Date: 2026-06-30 08:50:00

Tables: branches, settings, module_states, notifications, audit_logs
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "47f5f348"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── branches ──────────────────────────────────────────────────────
    op.create_table(
        "branches",
        sa.Column("id",         sa.Integer(),     nullable=False),
        sa.Column("name",       sa.String(100),   nullable=False),
        sa.Column("name_ar",    sa.String(100),   nullable=True),
        sa.Column("code",       sa.String(20),    nullable=False),
        sa.Column("is_active",  sa.Boolean(),     nullable=False, server_default="true"),
        sa.Column("timezone",   sa.String(50),    nullable=False, server_default="Africa/Cairo"),
        sa.Column("phone",      sa.String(20),    nullable=True),
        sa.Column("address",    sa.Text(),        nullable=True),
        sa.Column("gm_phone",   sa.String(20),    nullable=True),
        sa.Column("created_at", sa.DateTime(),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(),    nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    # ── settings ──────────────────────────────────────────────────────
    op.create_table(
        "settings",
        sa.Column("id",        sa.Integer(),   nullable=False),
        sa.Column("key",       sa.String(100), nullable=False),
        sa.Column("value",     sa.Text(),      nullable=False),
        sa.Column("branch_id", sa.Integer(),   nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", "branch_id"),
    )

    # ── module_states ─────────────────────────────────────────────────
    op.create_table(
        "module_states",
        sa.Column("id",          sa.Integer(),    nullable=False),
        sa.Column("module_key",  sa.String(50),   nullable=False),
        sa.Column("enabled",     sa.Boolean(),    nullable=False, server_default="true"),
        sa.Column("branch_id",   sa.Integer(),    nullable=True),
        sa.Column("changed_by",  sa.Integer(),    nullable=True),
        sa.Column("created_at",  sa.DateTime(),   nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.DateTime(),   nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"],  ["branches.id"], ondelete="CASCADE"),
        # FK to users — يُضاف بعد إنشاء users table في wego-core migration
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_key", "branch_id", name="uq_module_branch"),
    )
    op.create_index("ix_module_states_branch_id", "module_states", ["branch_id"])

    # ── notifications ─────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id",                  sa.Integer(),    nullable=False),
        sa.Column("user_id",             sa.Integer(),    nullable=False),
        sa.Column("branch_id",           sa.Integer(),    nullable=True),
        sa.Column("title",               sa.String(200),  nullable=False),
        sa.Column("body",                sa.Text(),       nullable=False),
        sa.Column("type",                sa.String(20),   nullable=False, server_default="info"),
        sa.Column("is_read",             sa.Boolean(),    nullable=False, server_default="false"),
        sa.Column("related_entity_type", sa.String(50),   nullable=True),
        sa.Column("related_entity_id",   sa.Integer(),    nullable=True),
        sa.Column("created_at",          sa.DateTime(),   nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",          sa.DateTime(),   nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id",  "notifications", ["user_id"])
    op.create_index("ix_notifications_branch_id", "notifications", ["branch_id"])
    op.create_index("ix_notifications_is_read",   "notifications", ["is_read"])

    # ── audit_logs ────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id",          sa.Integer(),    nullable=False),
        sa.Column("user_id",     sa.Integer(),    nullable=True),
        sa.Column("branch_id",   sa.Integer(),    nullable=True),
        sa.Column("action",      sa.String(100),  nullable=False),
        sa.Column("entity_type", sa.String(50),   nullable=False),
        sa.Column("entity_id",   sa.Integer(),    nullable=True),
        sa.Column("old_data",    sa.Text(),       nullable=True),
        sa.Column("new_data",    sa.Text(),       nullable=True),
        sa.Column("ip_address",  sa.String(45),   nullable=True),
        sa.Column("user_agent",  sa.String(500),  nullable=True),
        sa.Column("created_at",  sa.DateTime(),   nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.DateTime(),   nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_user_id",     "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_branch_id",   "audit_logs", ["branch_id"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_action",      "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("module_states")
    op.drop_table("settings")
    op.drop_table("branches")
