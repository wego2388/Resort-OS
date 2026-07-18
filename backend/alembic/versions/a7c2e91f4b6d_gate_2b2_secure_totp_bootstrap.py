"""Gate 2B2 secure TOTP bootstrap and one-time recovery codes.

Revision ID: a7c2e91f4b6d
Revises: 9989c0432ccc
Create Date: 2026-07-18 00:00:00.000000

The migration preserves every account and every existing TOTP secret.  It
marks only known development identities and mandatory-role accounts that are
not enrolled yet as requiring the explicit local bootstrap flow.  No printed
QR code or operational/financial record is touched.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c2e91f4b6d"
down_revision: Union[str, None] = "9989c0432ccc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEGACY_SEED_EMAILS = (
    "admin@resortos.local",
    "branch_admin@resortos.local",
    "accountant@resortos.local",
    "hr@resortos.local",
    "manager@resortos.local",
    "supervisor@resortos.local",
    "reception@resortos.local",
    "cashier@resortos.local",
    "waiter@resortos.local",
    "chef@resortos.local",
    "kitchen@resortos.local",
    "employee@resortos.local",
)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "two_factor_bootstrap_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("two_factor_enrollment_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "two_factor_enrollment_expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("two_factor_last_used_step", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "two_factor_recovery_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "code_hash",
            name="uq_2fa_recovery_user_code",
        ),
    )
    op.create_index(
        op.f("ix_two_factor_recovery_codes_user_id"),
        "two_factor_recovery_codes",
        ["user_id"],
        unique=False,
    )

    # Existing un-enrolled privileged users must receive an explicit token
    # from `python -m app.admin_bootstrap recover` before binding a factor.
    op.execute(
        sa.text(
            "UPDATE users SET two_factor_bootstrap_required = true "
            "WHERE role IN ('super_admin', 'accountant') "
            "AND COALESCE(two_factor_enabled, false) = false"
        )
    )
    # Old seed identities are publicly documented and use known development
    # credentials.  In non-development environments the application blocks
    # them until the operator rotates them through the bootstrap command.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE users SET two_factor_bootstrap_required = true "
            "WHERE email IN :emails"
        ).bindparams(sa.bindparam("emails", expanding=True)),
        {"emails": list(_LEGACY_SEED_EMAILS)},
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_two_factor_recovery_codes_user_id"),
        table_name="two_factor_recovery_codes",
    )
    op.drop_table("two_factor_recovery_codes")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "two_factor_last_used_step")
    op.drop_column("users", "two_factor_enrollment_expires_at")
    op.drop_column("users", "two_factor_enrollment_token_hash")
    op.drop_column("users", "two_factor_bootstrap_required")
