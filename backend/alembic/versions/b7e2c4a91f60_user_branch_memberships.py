"""session-scoped active branch and authorization memberships

Revision ID: b7e2c4a91f60
Revises: dc6bfb5b79e8
Create Date: 2026-07-26 21:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2c4a91f60"
down_revision: Union[str, None] = "dc6bfb5b79e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_branch_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "NOT is_default OR is_active",
            name="ck_user_branch_membership_default_active",
        ),
        sa.CheckConstraint(
            (
                "(is_active AND revoked_at IS NULL AND revoked_by IS NULL) OR "
                "((NOT is_active) AND revoked_at IS NOT NULL)"
            ),
            name="ck_user_branch_membership_revocation_state",
        ),
        sa.UniqueConstraint(
            "user_id",
            "branch_id",
            name="uq_user_branch_membership",
        ),
    )
    op.create_index(
        "ix_user_branch_memberships_user_id",
        "user_branch_memberships",
        ["user_id"],
    )
    op.create_index(
        "ix_user_branch_memberships_branch_id",
        "user_branch_memberships",
        ["branch_id"],
    )
    op.create_index(
        "ix_user_branch_memberships_active_lookup",
        "user_branch_memberships",
        ["user_id", "branch_id", "is_active"],
    )
    op.create_index(
        "uq_user_branch_membership_active_default",
        "user_branch_memberships",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_active AND is_default"),
        sqlite_where=sa.text("is_active = 1 AND is_default = 1"),
    )

    with op.batch_alter_table("refresh_tokens") as batch_op:
        batch_op.add_column(
            sa.Column(
                "active_branch_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_refresh_tokens_active_branch_id_branches",
            "branches",
            ["active_branch_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_refresh_tokens_user_family_active_branch",
            ["user_id", "family_public_id", "active_branch_id"],
        )

    # Employee.branch_id is a one-time migration source only.  It remains the
    # HR/payroll assignment and is never read by authorization after this.
    op.execute(sa.text("""
        INSERT INTO user_branch_memberships (
            user_id,
            branch_id,
            is_default,
            is_active,
            created_by,
            revoked_at,
            revoked_by,
            created_at,
            updated_at
        )
        SELECT
            employees.user_id,
            employees.branch_id,
            true,
            true,
            NULL,
            NULL,
            NULL,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM employees
        WHERE employees.user_id IS NOT NULL
    """))

    # Seed only ordinary live families whose default is both unique and points
    # to an active branch.  Super-admin with multiple branches remains an
    # explicit selection state; no first-id fallback is used.
    op.execute(sa.text("""
        UPDATE refresh_tokens
        SET active_branch_id = (
            SELECT memberships.branch_id
            FROM user_branch_memberships AS memberships
            JOIN branches
              ON branches.id = memberships.branch_id
             AND branches.is_active = true
            WHERE memberships.user_id = refresh_tokens.user_id
              AND memberships.is_active = true
              AND memberships.is_default = true
        )
        WHERE active_branch_id IS NULL
          AND EXISTS (
              SELECT 1
              FROM users
              WHERE users.id = refresh_tokens.user_id
                AND users.role <> 'super_admin'
          )
          AND 1 = (
              SELECT COUNT(*)
              FROM user_branch_memberships AS memberships
              JOIN branches
                ON branches.id = memberships.branch_id
               AND branches.is_active = true
              WHERE memberships.user_id = refresh_tokens.user_id
                AND memberships.is_active = true
                AND memberships.is_default = true
          )
    """))


def downgrade() -> None:
    # Maintenance-only after multi-branch assignment starts: membership
    # information cannot be represented by Employee.branch_id.
    with op.batch_alter_table("refresh_tokens") as batch_op:
        batch_op.drop_index("ix_refresh_tokens_user_family_active_branch")
        batch_op.drop_constraint(
            "fk_refresh_tokens_active_branch_id_branches",
            type_="foreignkey",
        )
        batch_op.drop_column("active_branch_id")

    op.drop_index(
        "uq_user_branch_membership_active_default",
        table_name="user_branch_memberships",
    )
    op.drop_index(
        "ix_user_branch_memberships_active_lookup",
        table_name="user_branch_memberships",
    )
    op.drop_index(
        "ix_user_branch_memberships_branch_id",
        table_name="user_branch_memberships",
    )
    op.drop_index(
        "ix_user_branch_memberships_user_id",
        table_name="user_branch_memberships",
    )
    op.drop_table("user_branch_memberships")
