"""Canonical case-insensitive user email identity.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""

import sqlalchemy as sa

from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    collision_count = connection.execute(sa.text("""
        SELECT COUNT(*)
        FROM (
            SELECT lower(trim(email)) AS canonical_email
            FROM users
            GROUP BY lower(trim(email))
            HAVING COUNT(*) > 1
        ) AS collisions
    """)).scalar_one()
    if collision_count:
        # Fail before changing any row and do not print email addresses/PII.
        raise RuntimeError(
            f"Cannot canonicalize user emails: {collision_count} case-insensitive collision group(s)"
        )

    connection.execute(sa.text("UPDATE users SET email = lower(trim(email))"))
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
