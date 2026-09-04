"""Payment collection channels (cash drawer / Visa CIB / Vodafone Cash / ...)

Revision ID: a7b3f2c8e9d1
Revises: e2f3a4b5c6d7
Create Date: 2026-08-16

Additive, forward-only. Adds:

  * ``payment_channels`` — branch-scoped collection channels a cashier picks
    at sale time (e.g. "الصندوق", "Visa CIB", "Vodafone Cash"). Each channel
    carries a mandatory GL account, an optional bank account, and
    is_default/is_active/sort_order. UNIQUE(branch_id, code) plus a partial
    unique index enforce "at most one default channel per (branch, method)".
    Channels are never deleted from the API — history depends on the row
    surviving, so disabling is the only retirement path.
  * ``payments.payment_channel_id`` / ``payment_channel_code`` /
    ``payment_channel_name`` / ``settlement_account_code`` — a historical
    snapshot of the channel used at sale time. A later edit to the channel
    (rename, GL change, disable) must never alter what a past sale/void
    posted to; the snapshot is the source of truth for that transaction,
    not a live join to ``payment_channels``.
  * ``beach_transactions`` — the same four snapshot columns, for the same
    reason (Beach sells directly against a channel, independent of the
    finance module's Payment row created alongside it).

Backfill: for every existing branch, a default channel per method is created
*only* from an account that already exists in that branch's chart of
accounts (``1100`` cash / ``1120`` card / ``1130`` wallet — the codes
``app.seed._seed_chart_of_accounts`` uses today). No account is invented and
no channel is created for a branch/method pair whose account is missing;
Beach/Dining sales for that branch/method keep working exactly as before
through the legacy environment-variable account resolution
(``resolve_payment_channel`` returns ``None`` when a branch has zero
channels for a method) until the owner configures a channel from the new
Finance screen.

Rollback honesty: downgrade drops the four snapshot columns from
``payments``/``beach_transactions`` and drops ``payment_channels`` entirely.
Once real sales have recorded a channel snapshot, a downgrade discards which
channel/GL account those historical sales actually posted to (the
``JournalLine`` entries themselves are untouched — only the convenience
snapshot on the source row is lost) and reopens legacy environment-variable
account resolution as the only path. No account, journal, or payment row is
deleted by either direction.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "a7b3f2c8e9d1"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


# (code, method, name_en, name_ar) — matches app.seed._seed_chart_of_accounts
_BACKFILL_CHANNELS = [
    ("1100", "cash",   "CASH",   "Cash Drawer",             "الصندوق / النقدية"),
    ("1120", "card",   "CARD",   "Card Collections",        "حساب وسيط تحصيلات الكارت"),
    ("1130", "wallet", "WALLET", "Electronic Collections",  "حساب وسيط تحصيلات إلكترونية"),
]


def upgrade() -> None:
    op.create_table(
        "payment_channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_ar", sa.String(length=200), nullable=True),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("gl_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("branch_id", "code", name="uq_payment_channel_branch_code"),
    )
    op.create_index("ix_payment_channels_branch_id", "payment_channels", ["branch_id"])
    op.create_index("ix_payment_channels_method", "payment_channels", ["method"])
    op.create_index("ix_payment_channels_gl_account_id", "payment_channels", ["gl_account_id"])
    op.create_index("ix_payment_channels_bank_account_id", "payment_channels", ["bank_account_id"])
    op.create_index(
        "uq_payment_channel_default_method", "payment_channels",
        ["branch_id", "method"], unique=True,
        postgresql_where=sa.text("is_default = true"),
        sqlite_where=sa.text("is_default = 1"),
    )

    for table in ("payments", "beach_transactions"):
        op.add_column(table, sa.Column(
            "payment_channel_id", sa.Integer(),
            sa.ForeignKey("payment_channels.id", ondelete="SET NULL"), nullable=True,
        ))
        op.add_column(table, sa.Column("payment_channel_code", sa.String(length=50), nullable=True))
        op.add_column(table, sa.Column("payment_channel_name", sa.String(length=200), nullable=True))
        op.add_column(table, sa.Column("settlement_account_code", sa.String(length=20), nullable=True))
        op.create_index(f"ix_{table}_payment_channel_id", table, ["payment_channel_id"])

    # ── Backfill: one default channel per (branch, method) only when the
    # matching legacy GL account already exists in that branch. Pure SQL —
    # no ORM session, no invented accounts, idempotent (re-running the
    # upgrade is impossible via alembic, but the INSERT is still scoped to
    # branches that don't already have that channel code).
    connection = op.get_bind()
    branch_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM branches")).fetchall()]
    for branch_id in branch_ids:
        for code, method, channel_code, name_en, name_ar in _BACKFILL_CHANNELS:
            account_row = connection.execute(
                sa.text(
                    "SELECT id FROM accounts WHERE branch_id = :branch_id AND code = :code "
                    "AND account_type = 'asset' AND is_active = true",
                ),
                {"branch_id": branch_id, "code": code},
            ).fetchone()
            if account_row is None:
                continue
            connection.execute(
                sa.text(
                    "INSERT INTO payment_channels "
                    "(branch_id, code, name, name_ar, method, gl_account_id, "
                    " is_default, is_active, sort_order, created_at, updated_at) "
                    "VALUES (:branch_id, :code, :name, :name_ar, :method, :gl_account_id, "
                    " true, true, 0, now(), now())",
                ),
                {
                    "branch_id": branch_id, "code": channel_code, "name": name_en,
                    "name_ar": name_ar, "method": method, "gl_account_id": account_row[0],
                },
            )


def downgrade() -> None:
    for table in ("payments", "beach_transactions"):
        op.drop_index(f"ix_{table}_payment_channel_id", table_name=table)
        op.drop_column(table, "settlement_account_code")
        op.drop_column(table, "payment_channel_name")
        op.drop_column(table, "payment_channel_code")
        op.drop_column(table, "payment_channel_id")

    op.drop_index("uq_payment_channel_default_method", table_name="payment_channels")
    op.drop_index("ix_payment_channels_bank_account_id", table_name="payment_channels")
    op.drop_index("ix_payment_channels_gl_account_id", table_name="payment_channels")
    op.drop_index("ix_payment_channels_method", table_name="payment_channels")
    op.drop_index("ix_payment_channels_branch_id", table_name="payment_channels")
    op.drop_table("payment_channels")
