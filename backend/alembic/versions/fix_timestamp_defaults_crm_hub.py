"""Fix missing server_default now() on created_at/updated_at for 7 CRM/hub tables

Same root cause and pattern as fix_timestamp_defaults_5tables.py (2026-07-01):
the ORM models (via TimestampMixin) declare `server_default=func.now()`, but
the hand-written migrations that created these 7 tables set plain
`nullable=False` timestamp columns with no `server_default` — SQLite-backed
tests never notice (Base.metadata.create_all() builds tables straight from
the model definitions, defaults included), but any real Postgres insert that
doesn't explicitly set created_at/updated_at fails with a NOT NULL violation.

Discovered 2026-07-03 while live-verifying a fix to the public booking-inquiry
form (POST /hub/contact) — the insert into contact_forms failed with exactly
this NOT NULL violation. A full information_schema query across the whole
database found 7 affected tables total, not just contact_forms: blog_posts,
call_notes, campaigns, contact_forms, guest_profiles, lead_sources, leads.
Fixing all 7 in one migration rather than one at a time.

Revision ID: fix_ts_crm_hub
Revises: f765b30eae0f
Create Date: 2026-07-03
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "fix_ts_crm_hub"
down_revision: Union[str, None] = "f765b30eae0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    "blog_posts", "call_notes", "campaigns", "contact_forms",
    "guest_profiles", "lead_sources", "leads",
]


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "created_at", server_default=sa.text("now()"))
        op.alter_column(table, "updated_at", server_default=sa.text("now()"))


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "created_at", server_default=None)
        op.alter_column(table, "updated_at", server_default=None)
