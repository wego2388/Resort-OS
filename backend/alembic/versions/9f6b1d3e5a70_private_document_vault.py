"""private encrypted document vault

Revision ID: 9f6b1d3e5a70
Revises: d2e4f6a8c0b1
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa

from app.core.encryption import EncryptedString


revision = "9f6b1d3e5a70"
down_revision = "d2e4f6a8c0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("doc_type", sa.String(length=50), nullable=False),
        sa.Column("visibility", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("storage_key", sa.String(length=160), nullable=False),
        sa.Column("original_filename", EncryptedString(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("replaces_document_id", sa.Integer(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("deleted_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.TIMESTAMP(), nullable=True),
        sa.CheckConstraint(
            "(scope = 'branch' AND employee_id IS NULL) OR "
            "(scope = 'employee' AND employee_id IS NOT NULL)",
            name="ck_documents_subject_scope",
        ),
        sa.CheckConstraint(
            "(scope = 'branch' AND visibility IN ('management', 'owner_visible')) OR "
            "(scope = 'employee' AND visibility IN ('hr_confidential', 'employee_visible'))",
            name="ck_documents_visibility_scope",
        ),
        sa.CheckConstraint(
            "expiry_date IS NULL OR issue_date IS NULL OR expiry_date >= issue_date",
            name="ck_documents_expiry_after_issue",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_documents_positive_size"),
        sa.CheckConstraint("version_number >= 1", name="ck_documents_positive_version"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["replaces_document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_documents_public_id", "documents", ["public_id"], unique=True)
    op.create_index("ix_documents_branch_id", "documents", ["branch_id"])
    op.create_index("ix_documents_employee_id", "documents", ["employee_id"])
    op.create_index("ix_documents_doc_type", "documents", ["doc_type"])
    op.create_index("ix_documents_expiry_date", "documents", ["expiry_date"])
    op.create_index("ix_documents_uploaded_by", "documents", ["uploaded_by"])
    op.create_index("ix_documents_replaces_document_id", "documents", ["replaces_document_id"])
    op.create_index(
        "ix_documents_branch_scope_active",
        "documents",
        ["branch_id", "scope", "doc_type"],
        postgresql_where=sa.text("deleted_at IS NULL AND superseded_at IS NULL"),
    )
    op.create_index(
        "ix_documents_employee_active",
        "documents",
        ["employee_id"],
        postgresql_where=sa.text("employee_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_documents_expiry_active",
        "documents",
        ["expiry_date"],
        postgresql_where=sa.text("expiry_date IS NOT NULL AND deleted_at IS NULL AND superseded_at IS NULL"),
    )

    op.create_table(
        "document_expiry_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("threshold_days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "threshold_days IN (-1, 7, 30, 60)",
            name="ck_document_expiry_notification_threshold",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "expiry_date",
            "threshold_days",
            name="uq_document_expiry_notification_band",
        ),
    )
    op.create_index(
        "ix_document_expiry_notifications_document_id",
        "document_expiry_notifications",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_expiry_notifications_document_id",
        table_name="document_expiry_notifications",
    )
    op.drop_table("document_expiry_notifications")
    op.drop_index("ix_documents_expiry_active", table_name="documents")
    op.drop_index("ix_documents_employee_active", table_name="documents")
    op.drop_index("ix_documents_branch_scope_active", table_name="documents")
    op.drop_index("ix_documents_replaces_document_id", table_name="documents")
    op.drop_index("ix_documents_uploaded_by", table_name="documents")
    op.drop_index("ix_documents_expiry_date", table_name="documents")
    op.drop_index("ix_documents_doc_type", table_name="documents")
    op.drop_index("ix_documents_employee_id", table_name="documents")
    op.drop_index("ix_documents_branch_id", table_name="documents")
    op.drop_index("ix_documents_public_id", table_name="documents")
    op.drop_table("documents")
