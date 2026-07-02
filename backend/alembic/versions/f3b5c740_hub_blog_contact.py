"""Hub: BlogPost, ContactForm

Revision ID: f3b5c740
Revises: c9f1a852
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "f3b5c740"
down_revision = "c9f1a852"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blog_posts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("slug", sa.String(300), nullable=False, unique=True),
        sa.Column("excerpt", sa.String(500), nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("cover_image", sa.String(300), nullable=True),
        sa.Column("meta_title", sa.String(300), nullable=True),
        sa.Column("meta_description", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("published_at", sa.DateTime, nullable=True),
        sa.Column("author_id", sa.Integer, nullable=False),
        sa.Column("views_count", sa.Integer, default=0, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "contact_forms",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(150), nullable=True),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("source_page", sa.String(100), nullable=True),
        sa.Column("lead_id", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), default="new", nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("contact_forms")
    op.drop_table("blog_posts")
