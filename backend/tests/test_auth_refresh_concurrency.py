"""PostgreSQL proof that one refresh token can be consumed only once.

SQLite cannot prove the conditional-DELETE behavior under real concurrent
transactions. This test creates a disposable PostgreSQL database and installs
a tiny test-only delay trigger so both requests read the same old token before
the first DELETE commits.

Run explicitly with an admin DSN:

    AUTH_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://.../postgres \
        pytest tests/test_auth_refresh_concurrency.py -v
"""
from __future__ import annotations

import os
import threading
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker


AUTH_CONCURRENCY_TEST_ADMIN_URL = os.environ.get("AUTH_CONCURRENCY_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not AUTH_CONCURRENCY_TEST_ADMIN_URL,
    reason=(
        "Postgres-only refresh rotation test — set "
        "AUTH_CONCURRENCY_TEST_ADMIN_URL to an admin PostgreSQL DSN."
    ),
)


@pytest.fixture
def pg_engine():
    admin_engine = sa.create_engine(
        AUTH_CONCURRENCY_TEST_ADMIN_URL,
        isolation_level="AUTOCOMMIT",
    )
    db_name = f"resort_os_auth_conctest_{uuid.uuid4().hex[:10]}"
    base_url = AUTH_CONCURRENCY_TEST_ADMIN_URL.rsplit("/", 1)[0]
    target_url = f"{base_url}/{db_name}"

    with admin_engine.connect() as connection:
        connection.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    from app.core.database import Base
    import app.core.kernel.models.user  # noqa: F401

    engine = sa.create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(sa.text("""
            CREATE FUNCTION gate2b_slow_refresh_delete()
            RETURNS trigger AS $$
            BEGIN
                PERFORM pg_sleep(0.25);
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql
        """))
        connection.execute(sa.text("""
            CREATE TRIGGER gate2b_slow_refresh_delete_trigger
            BEFORE DELETE ON refresh_tokens
            FOR EACH ROW EXECUTE FUNCTION gate2b_slow_refresh_delete()
        """))

    try:
        yield engine
    finally:
        engine.dispose()
        cleanup_engine = sa.create_engine(
            AUTH_CONCURRENCY_TEST_ADMIN_URL,
            isolation_level="AUTOCOMMIT",
        )
        with cleanup_engine.connect() as connection:
            connection.execute(sa.text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
            ))
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        cleanup_engine.dispose()


@pytest.fixture
def Session(pg_engine):
    return sessionmaker(bind=pg_engine, autoflush=False, autocommit=False)


def test_concurrent_rotation_mints_exactly_one_replacement(Session):
    from app.core.config import settings
    from app.core.kernel.auth.service import AuthService
    from app.core.kernel.models.user import RefreshToken, User
    from app.core.kernel.security import get_password_hash

    setup_db = Session()
    try:
        user = User(
            email=f"refresh-race-{uuid.uuid4().hex}@test.local",
            password_hash=get_password_hash("Current@12345"),
            full_name="Refresh Race",
            role="cashier",
            is_active=True,
        )
        setup_db.add(user)
        setup_db.commit()
        setup_db.refresh(user)
        user_id = user.id
        old_token = AuthService(setup_db, User, settings).create_refresh_token(user_id)
    finally:
        setup_db.close()

    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}

    def rotate(key: str) -> None:
        db = Session()
        try:
            barrier.wait(timeout=5)
            outcomes[key] = AuthService(db, User, settings).rotate_refresh_token(old_token)
        except Exception as exc:  # noqa: BLE001 — asserted after both threads finish
            db.rollback()
            outcomes[key] = exc
        finally:
            db.close()

    first = threading.Thread(target=rotate, args=("first",))
    second = threading.Thread(target=rotate, args=("second",))
    first.start()
    second.start()
    first.join(timeout=15)
    second.join(timeout=15)

    assert not first.is_alive() and not second.is_alive(), "refresh rotation deadlocked"
    assert set(outcomes) == {"first", "second"}
    assert not any(isinstance(value, Exception) for value in outcomes.values()), outcomes
    successes = [value for value in outcomes.values() if value is not None]
    failures = [value for value in outcomes.values() if value is None]
    assert len(successes) == 1, outcomes
    assert len(failures) == 1, outcomes

    verify_db = Session()
    try:
        rows = verify_db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
        ).all()
        assert len(rows) == 1
        assert rows[0].token_hash != AuthService._hash_token(old_token)
    finally:
        verify_db.close()
