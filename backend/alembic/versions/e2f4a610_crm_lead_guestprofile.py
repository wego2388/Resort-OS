"""CRM: Lead, CallNote, Campaign, LeadSource, GuestProfile

Revision ID: e2f4a610
Revises: c9f1a852
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "e2f4a610"
down_revision = "c9f1a852"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(150), nullable=True),
        sa.Column("nationality", sa.String(50), nullable=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("lead_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("interest", sa.String(50), default="other", nullable=False),
        sa.Column("stage", sa.String(30), default="new", nullable=False),
        sa.Column("assigned_to", sa.Integer, nullable=True),
        sa.Column("expected_value", sa.Numeric(14, 2), default=0, nullable=False),
        sa.Column("won_at", sa.DateTime, nullable=True),
        sa.Column("lost_at", sa.DateTime, nullable=True),
        sa.Column("lost_reason", sa.String(300), nullable=True),
        sa.Column("booking_id", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "call_notes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", sa.Integer, sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(10), default="outbound", nullable=False),
        sa.Column("duration_min", sa.Integer, nullable=True),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("outcome", sa.String(50), default="no_decision", nullable=False),
        sa.Column("callback_at", sa.DateTime, nullable=True),
        sa.Column("called_by", sa.Integer, nullable=False),
        sa.Column("called_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("campaign_type", sa.String(30), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("budget", sa.Numeric(12, 2), default=0, nullable=False),
        sa.Column("revenue_attributed", sa.Numeric(14, 2), default=0, nullable=False),
        sa.Column("leads_generated", sa.Integer, default=0, nullable=False),
        sa.Column("status", sa.String(20), default="planned", nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "guest_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("email", sa.String(150), nullable=True),
        sa.Column("national_id", sa.String(20), nullable=True),
        sa.Column("nationality", sa.String(50), nullable=True),
        sa.Column("birthday", sa.Date, nullable=True),
        sa.Column("total_visits", sa.Integer, default=0, nullable=False),
        sa.Column("avg_spend", sa.Numeric(12, 2), default=0, nullable=False),
        sa.Column("vip_flag", sa.Boolean, default=False, nullable=False),
        sa.Column("last_stay", sa.Date, nullable=True),
        sa.Column("preferences", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("branch_id", "phone", name="uq_guest_profile_branch_phone"),
    )


def downgrade() -> None:
    op.drop_table("guest_profiles")
    op.drop_table("campaigns")
    op.drop_table("call_notes")
    op.drop_table("leads")
    op.drop_table("lead_sources")
