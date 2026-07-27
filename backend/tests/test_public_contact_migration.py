"""PostgreSQL migration proof for CL-02B's in-place PII encryption.

Enable with an explicit admin DSN:

    CL02B_MIGRATION_TEST_ADMIN_URL=postgresql+psycopg://.../postgres \
        pytest tests/test_public_contact_migration.py -v
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest


ADMIN_URL = os.environ.get("CL02B_MIGRATION_TEST_ADMIN_URL")
pytestmark = pytest.mark.skipif(
    not ADMIN_URL,
    reason="set CL02B_MIGRATION_TEST_ADMIN_URL to run PostgreSQL migrations",
)

PRE_PRIVACY_REVISION = "b7e2c4a91f60"
PRIVACY_REVISION = "c4d8e2f6a901"


@pytest.fixture
def migrated_db_url():
    import sqlalchemy as sa
    from sqlalchemy.engine import make_url

    admin_url = make_url(ADMIN_URL)
    db_name = f"resort_os_cl02b_{uuid.uuid4().hex[:12]}"
    target_url = admin_url.set(database=db_name)
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    try:
        yield target_url.render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.execute(
                sa.text(
                    """
                    SELECT pg_terminate_backend(pid)
                      FROM pg_stat_activity
                     WHERE datname = :database_name
                       AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": db_name},
            )
            connection.execute(sa.text(f'DROP DATABASE "{db_name}"'))
        admin.dispose()


def _config(db_url: str):
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


@contextmanager
def _database_url(db_url: str):
    from app.core.config import settings

    original = settings.DATABASE_URL
    settings.DATABASE_URL = db_url
    try:
        yield
    finally:
        settings.DATABASE_URL = original


def _upgrade(db_url: str, revision: str) -> None:
    from alembic import command

    with _database_url(db_url):
        command.upgrade(_config(db_url), revision)


def _downgrade(db_url: str, revision: str) -> None:
    from alembic import command

    with _database_url(db_url):
        command.downgrade(_config(db_url), revision)


def _seed_legacy_plaintext(db_url: str) -> tuple[int, int]:
    import sqlalchemy as sa

    engine = sa.create_engine(db_url)
    with engine.begin() as connection:
        branch_id = connection.execute(sa.text(
            """
            INSERT INTO branches (name, code)
            VALUES ('CL02B Migration Branch', :code)
            RETURNING id
            """
        ), {"code": f"CL02B-{uuid.uuid4().hex[:8]}"}).scalar_one()
        contact_id = connection.execute(sa.text(
            """
            INSERT INTO contact_forms (
                branch_id, full_name, phone, email, subject, message,
                source_page, status, created_at, updated_at
            )
            VALUES (
                :branch_id, 'Legacy Contact', '+201001234567',
                'legacy@example.com', 'Legacy subject', 'Legacy message',
                '/contact', 'new', now(), now()
            )
            RETURNING id
            """
        ), {"branch_id": branch_id}).scalar_one()
        lead_id = connection.execute(sa.text(
            """
            INSERT INTO leads (
                branch_id, full_name, phone, email, interest, stage,
                expected_value, notes, created_at, updated_at
            )
            VALUES (
                :branch_id, 'Legacy Lead', '+201009876543',
                'lead@example.com', 'other', 'new', 0,
                'Legacy lead notes', now(), now()
            )
            RETURNING id
            """
        ), {"branch_id": branch_id}).scalar_one()
    engine.dispose()
    return contact_id, lead_id


def test_fresh_chain_reaches_privacy_head(migrated_db_url):
    import sqlalchemy as sa

    _upgrade(migrated_db_url, "head")
    engine = sa.create_engine(migrated_db_url)
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one() == PRIVACY_REVISION
    engine.dispose()


def test_legacy_plaintext_encrypts_and_pre_use_round_trip_is_safe(
    migrated_db_url,
):
    import sqlalchemy as sa
    from cryptography.fernet import Fernet
    from app.core.config import settings

    _upgrade(migrated_db_url, PRE_PRIVACY_REVISION)
    contact_id, lead_id = _seed_legacy_plaintext(migrated_db_url)
    _upgrade(migrated_db_url, PRIVACY_REVISION)

    engine = sa.create_engine(migrated_db_url)
    with engine.connect() as connection:
        contact = connection.execute(sa.text(
            """
            SELECT full_name, phone, email, subject, message,
                   public_reference, service_contact_authorized,
                   marketing_consent, retention_until
              FROM contact_forms
             WHERE id = :row_id
            """
        ), {"row_id": contact_id}).mappings().one()
        lead = connection.execute(sa.text(
            """
            SELECT full_name, phone, email, notes, marketing_consent
              FROM leads
             WHERE id = :row_id
            """
        ), {"row_id": lead_id}).mappings().one()

    fernet = Fernet(settings.FIELD_ENCRYPTION_KEY.encode("ascii"))
    assert fernet.decrypt(contact["full_name"].encode()).decode() == "Legacy Contact"
    assert fernet.decrypt(contact["phone"].encode()).decode() == "+201001234567"
    assert fernet.decrypt(contact["email"].encode()).decode() == "legacy@example.com"
    assert fernet.decrypt(contact["subject"].encode()).decode() == "Legacy subject"
    assert fernet.decrypt(contact["message"].encode()).decode() == "Legacy message"
    assert fernet.decrypt(lead["full_name"].encode()).decode() == "Legacy Lead"
    assert fernet.decrypt(lead["notes"].encode()).decode() == "Legacy lead notes"
    assert contact["public_reference"] == f"legacy_contact_{contact_id}"
    assert contact["service_contact_authorized"] is False
    assert contact["marketing_consent"] is False
    assert contact["retention_until"] is not None
    assert lead["marketing_consent"] is False

    # Before any new-contract row exists, downgrade decrypts the legacy rows
    # and restores the old shape without data loss.
    _downgrade(migrated_db_url, PRE_PRIVACY_REVISION)
    with engine.connect() as connection:
        contact = connection.execute(sa.text(
            "SELECT full_name, phone, email, subject, message "
            "FROM contact_forms WHERE id = :row_id"
        ), {"row_id": contact_id}).mappings().one()
        lead = connection.execute(sa.text(
            "SELECT full_name, phone, email, notes "
            "FROM leads WHERE id = :row_id"
        ), {"row_id": lead_id}).mappings().one()
        privacy_column_exists = connection.execute(sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = current_schema()
                   AND table_name = 'contact_forms'
                   AND column_name = 'service_disclosure_version'
            )
            """
        )).scalar_one()
    assert tuple(contact.values()) == (
        "Legacy Contact",
        "+201001234567",
        "legacy@example.com",
        "Legacy subject",
        "Legacy message",
    )
    assert tuple(lead.values()) == (
        "Legacy Lead",
        "+201009876543",
        "lead@example.com",
        "Legacy lead notes",
    )
    assert privacy_column_exists is False

    _upgrade(migrated_db_url, "head")
    engine.dispose()
