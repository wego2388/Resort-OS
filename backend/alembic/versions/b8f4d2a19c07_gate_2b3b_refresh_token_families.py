"""Gate 2B3B — refresh-token families + replay-detection tombstones

Revision ID: b8f4d2a19c07
Revises: ad7ed1e7329b
Create Date: 2026-07-19

Additive, forward-only. Adds the family/lineage + tombstone columns to
``refresh_tokens`` (see app.core.kernel.models.user.RefreshToken) and gives
every pre-existing refresh row its *own* isolated family — never one shared
family for all legacy rows (a shared family would let one legacy token's
replay revoke unrelated users' sessions). The backfill is done in Python so
it is identical on PostgreSQL and SQLite and needs no DB-specific random/uuid
function.

Rollback honesty: once the application starts rotating the new families,
a downgrade drops the family/tombstone columns, so replay detection and the
self-service session list stop working and any in-flight family lineage is
lost. Existing refresh *tokens* keep working as opaque bearer credentials
(token_hash/expires_at are untouched); only the family-level hardening is
removed. No data that predates this migration is destroyed by the upgrade.
"""
from __future__ import annotations

import secrets

import sqlalchemy as sa
from alembic import op


revision = "b8f4d2a19c07"
down_revision = "ad7ed1e7329b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add columns. The two NOT NULL string columns arrive with a "" server
    #    default so the ADD COLUMN itself never violates NOT NULL on existing
    #    rows; the backfill immediately replaces "" with real random values.
    op.add_column(
        "refresh_tokens",
        sa.Column("family_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("family_public_id", sa.String(length=32), nullable=False, server_default=""),
    )
    op.add_column("refresh_tokens", sa.Column("family_started_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("refresh_tokens", sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("refresh_tokens", sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("refresh_tokens", sa.Column("successor_token_hash", sa.String(length=64), nullable=True))
    op.add_column("refresh_tokens", sa.Column("user_agent", sa.String(length=255), nullable=True))

    # 2) Deterministic-per-row backfill: one fresh, isolated family per legacy
    #    token, and family_started_at seeded from the row's own created_at.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM refresh_tokens WHERE family_id = ''")).fetchall()
    for (row_id,) in rows:
        bind.execute(
            sa.text(
                "UPDATE refresh_tokens SET family_id = :fid, family_public_id = :pid, "
                "family_started_at = created_at WHERE id = :id"
            ),
            {"fid": secrets.token_hex(16), "pid": secrets.token_hex(16), "id": row_id},
        )

    # 3) Indexes for the two hot lookup paths: revocation by family_id and the
    #    self-service list/revoke by family_public_id.
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_family_public_id", "refresh_tokens", ["family_public_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_family_public_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "user_agent")
    op.drop_column("refresh_tokens", "successor_token_hash")
    op.drop_column("refresh_tokens", "revoked_at")
    op.drop_column("refresh_tokens", "consumed_at")
    op.drop_column("refresh_tokens", "family_started_at")
    op.drop_column("refresh_tokens", "family_public_id")
    op.drop_column("refresh_tokens", "family_id")
