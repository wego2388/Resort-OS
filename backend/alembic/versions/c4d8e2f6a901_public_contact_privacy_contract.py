"""public contact privacy, consent, idempotency, retention, and PII encryption

Revision ID: c4d8e2f6a901
Revises: b7e2c4a91f60
Create Date: 2026-07-26 22:15:00.000000

This is deliberately a forward migration rather than an edit to the original
Hub/CRM revisions.  Existing plaintext contact/lead PII is encrypted in place;
already-encrypted values are detected and left unchanged.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet, InvalidToken

revision: str = "c4d8e2f6a901"
down_revision: Union[str, None] = "b7e2c4a91f60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PII_COLUMNS = {
    "contact_forms": ("full_name", "phone", "email", "subject", "message"),
    "leads": ("full_name", "phone", "email", "notes"),
}


def _fernet_for_existing_rows() -> Fernet:
    from app.core.config import settings  # noqa: PLC0415

    if not settings.FIELD_ENCRYPTION_KEY:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY is required to migrate existing public-contact PII"
        )
    return Fernet(settings.FIELD_ENCRYPTION_KEY.encode("ascii"))


def _transform_existing_pii(*, encrypt: bool) -> None:
    """Encrypt/decrypt known columns without double-transforming values."""
    bind = op.get_bind()
    fernet: Fernet | None = None

    for table_name, columns in _PII_COLUMNS.items():
        selected = ", ".join(["id", *columns])
        rows = bind.execute(
            sa.text(f"SELECT {selected} FROM {table_name} ORDER BY id")
        ).mappings()
        for row in rows:
            updates: dict[str, str] = {}
            for column_name in columns:
                value = row[column_name]
                if value in (None, ""):
                    continue
                if fernet is None:
                    fernet = _fernet_for_existing_rows()
                raw = value.encode("utf-8")
                try:
                    plaintext = fernet.decrypt(raw).decode("utf-8")
                    already_encrypted = True
                except InvalidToken:
                    plaintext = value
                    already_encrypted = False

                if encrypt and not already_encrypted:
                    updates[column_name] = fernet.encrypt(raw).decode("ascii")
                elif not encrypt and already_encrypted:
                    updates[column_name] = plaintext

            if updates:
                assignments = ", ".join(
                    f"{column_name} = :{column_name}"
                    for column_name in updates
                )
                bind.execute(
                    sa.text(
                        f"UPDATE {table_name} SET {assignments} WHERE id = :row_id"
                    ),
                    {**updates, "row_id": row["id"]},
                )


def upgrade() -> None:
    # Widen before encrypting: Fernet ciphertext is longer than plaintext.
    op.alter_column(
        "contact_forms",
        "full_name",
        existing_type=sa.String(200),
        type_=sa.String(512),
        nullable=True,
    )
    op.alter_column(
        "contact_forms",
        "phone",
        existing_type=sa.String(20),
        type_=sa.String(255),
        existing_nullable=True,
    )
    op.alter_column(
        "contact_forms",
        "email",
        existing_type=sa.String(150),
        type_=sa.String(512),
        existing_nullable=True,
    )
    op.alter_column(
        "contact_forms",
        "subject",
        existing_type=sa.String(200),
        type_=sa.String(512),
        nullable=True,
    )
    op.alter_column(
        "contact_forms",
        "message",
        existing_type=sa.Text(),
        type_=sa.String(),
        nullable=True,
    )

    op.add_column(
        "contact_forms",
        sa.Column("public_reference", sa.String(48), nullable=True),
    )
    op.add_column(
        "contact_forms",
        sa.Column(
            "source",
            sa.String(30),
            nullable=False,
            server_default="legacy_website",
        ),
    )
    op.add_column(
        "contact_forms",
        sa.Column(
            "purpose",
            sa.String(40),
            nullable=False,
            server_default="general_inquiry",
        ),
    )
    op.add_column(
        "contact_forms",
        sa.Column(
            "language",
            sa.String(5),
            nullable=False,
            server_default="ar",
        ),
    )
    op.add_column(
        "contact_forms",
        sa.Column(
            "service_contact_authorized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "contact_forms",
        sa.Column("service_disclosure_version", sa.String(40), nullable=True),
    )
    op.add_column(
        "contact_forms",
        sa.Column("service_contact_authorized_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "contact_forms",
        sa.Column(
            "marketing_consent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "contact_forms",
        sa.Column("marketing_consent_version", sa.String(40), nullable=True),
    )
    op.add_column(
        "contact_forms",
        sa.Column("marketing_consent_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "contact_forms",
        sa.Column("idempotency_key_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "contact_forms",
        sa.Column("payload_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "contact_forms",
        sa.Column("requester_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "contact_forms",
        sa.Column("retention_until", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "contact_forms",
        sa.Column("purged_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "contact_forms",
        sa.Column(
            "crm_sync_status",
            sa.String(20),
            nullable=False,
            server_default="not_requested",
        ),
    )

    bind = op.get_bind()
    bind.execute(sa.text(
        """
        UPDATE contact_forms
           SET public_reference = 'legacy_contact_' || id::text,
               retention_until = created_at + INTERVAL '180 days',
               crm_sync_status = CASE
                   WHEN lead_id IS NOT NULL THEN 'legacy_converted'
                   ELSE 'not_requested'
               END
        """
    ))
    op.alter_column("contact_forms", "public_reference", nullable=False)
    op.alter_column("contact_forms", "retention_until", nullable=False)

    op.create_index(
        "ix_contact_forms_public_reference",
        "contact_forms",
        ["public_reference"],
        unique=True,
    )
    op.create_index(
        "uq_contact_forms_branch_idempotency",
        "contact_forms",
        ["branch_id", "idempotency_key_hash"],
        unique=True,
        postgresql_where=sa.text("idempotency_key_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_contact_forms_requester_hash",
        "contact_forms",
        ["requester_hash"],
    )
    op.create_index(
        "ix_contact_forms_retention_until",
        "contact_forms",
        ["retention_until"],
    )
    op.create_index(
        "ix_contact_forms_retention_due",
        "contact_forms",
        ["retention_until", "purged_at"],
    )

    op.alter_column(
        "leads",
        "full_name",
        existing_type=sa.String(200),
        type_=sa.String(512),
        nullable=True,
    )
    op.alter_column(
        "leads",
        "phone",
        existing_type=sa.String(20),
        type_=sa.String(255),
        existing_nullable=True,
    )
    op.alter_column(
        "leads",
        "email",
        existing_type=sa.String(150),
        type_=sa.String(512),
        existing_nullable=True,
    )
    op.alter_column(
        "leads",
        "notes",
        existing_type=sa.Text(),
        type_=sa.String(),
        existing_nullable=True,
    )
    op.add_column(
        "leads",
        sa.Column("public_contact_form_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("purpose", sa.String(40), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "marketing_consent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "leads",
        sa.Column("marketing_consent_version", sa.String(40), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("marketing_consent_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("retention_until", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("purged_at", sa.DateTime(), nullable=True),
    )
    op.create_foreign_key(
        "fk_leads_public_contact_form_id_contact_forms",
        "leads",
        "contact_forms",
        ["public_contact_form_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_leads_public_contact_form_id",
        "leads",
        ["public_contact_form_id"],
        unique=True,
    )
    op.create_index(
        "ix_leads_retention_until",
        "leads",
        ["retention_until"],
    )

    _transform_existing_pii(encrypt=True)


def downgrade() -> None:
    bind = op.get_bind()
    new_contact_count = bind.execute(sa.text(
        """
        SELECT count(*)
          FROM contact_forms
         WHERE idempotency_key_hash IS NOT NULL
            OR service_disclosure_version IS NOT NULL
            OR purged_at IS NOT NULL
        """
    )).scalar_one()
    public_lead_count = bind.execute(sa.text(
        """
        SELECT count(*)
          FROM leads
         WHERE public_contact_form_id IS NOT NULL
            OR purged_at IS NOT NULL
        """
    )).scalar_one()
    if new_contact_count or public_lead_count:
        raise RuntimeError(
            "Cannot downgrade public-contact privacy contract after new or "
            "purged public data exists; restore a pre-upgrade backup instead."
        )

    _transform_existing_pii(encrypt=False)

    op.drop_index("ix_leads_retention_until", table_name="leads")
    op.drop_index("ix_leads_public_contact_form_id", table_name="leads")
    op.drop_constraint(
        "fk_leads_public_contact_form_id_contact_forms",
        "leads",
        type_="foreignkey",
    )
    for column_name in (
        "purged_at",
        "retention_until",
        "marketing_consent_at",
        "marketing_consent_version",
        "marketing_consent",
        "purpose",
        "public_contact_form_id",
    ):
        op.drop_column("leads", column_name)
    op.alter_column(
        "leads",
        "notes",
        existing_type=sa.String(),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "leads",
        "email",
        existing_type=sa.String(512),
        type_=sa.String(150),
        existing_nullable=True,
    )
    op.alter_column(
        "leads",
        "phone",
        existing_type=sa.String(255),
        type_=sa.String(20),
        existing_nullable=True,
    )
    op.alter_column(
        "leads",
        "full_name",
        existing_type=sa.String(512),
        type_=sa.String(200),
        nullable=False,
    )

    op.drop_index("ix_contact_forms_retention_due", table_name="contact_forms")
    op.drop_index("ix_contact_forms_retention_until", table_name="contact_forms")
    op.drop_index("ix_contact_forms_requester_hash", table_name="contact_forms")
    op.drop_index(
        "uq_contact_forms_branch_idempotency",
        table_name="contact_forms",
    )
    op.drop_index("ix_contact_forms_public_reference", table_name="contact_forms")
    for column_name in (
        "crm_sync_status",
        "purged_at",
        "retention_until",
        "requester_hash",
        "payload_hash",
        "idempotency_key_hash",
        "marketing_consent_at",
        "marketing_consent_version",
        "marketing_consent",
        "service_contact_authorized_at",
        "service_disclosure_version",
        "service_contact_authorized",
        "language",
        "purpose",
        "source",
        "public_reference",
    ):
        op.drop_column("contact_forms", column_name)
    op.alter_column(
        "contact_forms",
        "message",
        existing_type=sa.String(),
        type_=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "contact_forms",
        "subject",
        existing_type=sa.String(512),
        type_=sa.String(200),
        nullable=False,
    )
    op.alter_column(
        "contact_forms",
        "email",
        existing_type=sa.String(512),
        type_=sa.String(150),
        existing_nullable=True,
    )
    op.alter_column(
        "contact_forms",
        "phone",
        existing_type=sa.String(255),
        type_=sa.String(20),
        existing_nullable=True,
    )
    op.alter_column(
        "contact_forms",
        "full_name",
        existing_type=sa.String(512),
        type_=sa.String(200),
        nullable=False,
    )
