"""privacy-minimised chat metadata and approved public facts

Revision ID: dc6bfb5b79e8
Revises: f1a9c3d7e825
Create Date: 2026-07-26 00:00:00.000000

Raw guest messages and model replies are intentionally not persisted.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "dc6bfb5b79e8"
down_revision: Union[str, None] = "f1a9c3d7e825"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("public_reference", sa.String(48), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "language",
            sa.String(5),
            nullable=False,
            server_default="ar",
        ),
        sa.Column("visitor_page", sa.String(200), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("user_rating", sa.Integer(), nullable=True),
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "prompt_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "output_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "language IN ('ar','en','ru','it')",
            name="ck_chat_conversations_language",
        ),
        sa.CheckConstraint(
            "status IN ('active','completed')",
            name="ck_chat_conversations_status",
        ),
        sa.CheckConstraint(
            "user_rating IS NULL OR user_rating BETWEEN 1 AND 5",
            name="ck_chat_conversations_rating",
        ),
        sa.CheckConstraint(
            "message_count >= 0 AND prompt_tokens >= 0 AND output_tokens >= 0",
            name="ck_chat_conversations_usage_nonnegative",
        ),
        sa.UniqueConstraint(
            "public_reference",
            name="uq_chat_conversations_public_reference",
        ),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_chat_conversations_token_hash",
        ),
    )
    op.create_index(
        "ix_chat_conversations_branch_id",
        "chat_conversations",
        ["branch_id"],
    )
    op.create_index(
        "ix_chat_conversations_public_reference",
        "chat_conversations",
        ["public_reference"],
    )
    op.create_index(
        "ix_chat_conversations_token_hash",
        "chat_conversations",
        ["token_hash"],
    )
    op.create_index(
        "ix_chat_conversations_expires_at",
        "chat_conversations",
        ["expires_at"],
    )
    op.create_index(
        "ix_chat_conversations_branch_status_created",
        "chat_conversations",
        ["branch_id", "status", "created_at"],
    )

    op.create_table(
        "chat_public_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fact_key", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("source_reference", sa.String(500), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('draft','approved','retired')",
            name="ck_chat_public_facts_status",
        ),
        sa.CheckConstraint(
            "status != 'approved' OR approved_at IS NOT NULL",
            name="ck_chat_public_facts_approval_timestamp",
        ),
        sa.UniqueConstraint(
            "branch_id",
            "fact_key",
            name="uq_chat_public_facts_branch_key",
        ),
    )
    op.create_index(
        "ix_chat_public_facts_branch_id",
        "chat_public_facts",
        ["branch_id"],
    )
    op.create_index(
        "ix_chat_public_facts_branch_status_expiry",
        "chat_public_facts",
        ["branch_id", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_public_facts_branch_status_expiry",
        table_name="chat_public_facts",
    )
    op.drop_index(
        "ix_chat_public_facts_branch_id",
        table_name="chat_public_facts",
    )
    op.drop_table("chat_public_facts")

    op.drop_index(
        "ix_chat_conversations_branch_status_created",
        table_name="chat_conversations",
    )
    op.drop_index(
        "ix_chat_conversations_expires_at",
        table_name="chat_conversations",
    )
    op.drop_index(
        "ix_chat_conversations_token_hash",
        table_name="chat_conversations",
    )
    op.drop_index(
        "ix_chat_conversations_public_reference",
        table_name="chat_conversations",
    )
    op.drop_index(
        "ix_chat_conversations_branch_id",
        table_name="chat_conversations",
    )
    op.drop_table("chat_conversations")
