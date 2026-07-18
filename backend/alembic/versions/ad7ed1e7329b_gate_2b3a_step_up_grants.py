"""Gate 2B3A: DB-backed one-time step-up grants for the control plane.

Revision ID: ad7ed1e7329b
Revises: a7c2e91f4b6d
Create Date: 2026-07-18 00:00:00.000000

Adds a single new table, `step_up_grants`. No existing table or column is
touched. A grant is a short-lived, hashed, one-time proof that the current
session holder recently re-proved their password (and TOTP/recovery code
where 2FA is enabled) for one specific, hashed operation scope -- it is not
an authorization cache and carries no business data (no setting value, no
free-text reason) itself.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ad7ed1e7329b"
down_revision: Union[str, None] = "a7c2e91f4b6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "step_up_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        # Non-secret, safe to log/display for support/audit correlation —
        # never usable to consume the grant itself (that needs token_hash).
        sa.Column("public_reference", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        # SHA-256 of the canonical (deterministic JSON) operation scope —
        # binds the grant to the exact mutation it was issued for.
        sa.Column("scope_hash", sa.String(length=64), nullable=False),
        # SHA-256 of the opaque bearer token shown to the caller once.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        # SHA-256 of the access token that requested the grant — binds the
        # grant to that browser session, not just to the user_id.
        sa.Column("access_token_hash", sa.String(length=64), nullable=False),
        sa.Column("assurance_method", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_step_up_grants_token_hash"),
    )
    op.create_index(
        op.f("ix_step_up_grants_user_id"), "step_up_grants", ["user_id"], unique=False,
    )
    op.create_index(
        op.f("ix_step_up_grants_expires_at"), "step_up_grants", ["expires_at"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_step_up_grants_expires_at"), table_name="step_up_grants")
    op.drop_index(op.f("ix_step_up_grants_user_id"), table_name="step_up_grants")
    op.drop_table("step_up_grants")
