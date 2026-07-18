"""
tests/test_refresh_family_concurrency.py
Postgres-only real-concurrency proof for Gate 2B3B's refresh-token family
rotation + replay detection (docs/audits/gate-2b3b-auth-audit-session-defense.md).

AuthService.rotate_refresh_token()'s atomicity claim ("exactly one of two
concurrent refreshes of the same token mints a successor", and "a session
revoke racing a refresh never revives the session") rests entirely on a single
conditional UPDATE's own affected-row-count under a real Postgres engine with
real concurrent transactions. SQLite has no meaningful concurrent-transaction
story (single writer, whole-database lock), so tests/test_api/
test_auth_session_security.py can only prove the *contract* deterministically
(one thread, sequential calls), not genuine race-condition safety.

Mirrors tests/test_step_up_concurrency.py / test_super_admin_concurrency.py
exactly: an admin connection creates a disposable per-test throwaway database,
tables are built via Base.metadata.create_all() (no Alembic needed here — this
is about the UPDATE's row-count semantics, not migration correctness), and the
database is dropped at the end regardless of outcome.

Usage — set an admin Postgres DSN before running:

    REFRESH_FAMILY_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_refresh_family_concurrency.py -v

Skips automatically (does not fail, does not affect `pytest tests/`'s
100%-green requirement) when that env var is unset. Deliberately a **separate**
env var from STEP_UP_CONCURRENCY_TEST_ADMIN_URL / SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL
— different gate, different throwaway database.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

REFRESH_FAMILY_CONCURRENCY_TEST_ADMIN_URL = os.environ.get(
    "REFRESH_FAMILY_CONCURRENCY_TEST_ADMIN_URL",
)

pytestmark = pytest.mark.skipif(
    not REFRESH_FAMILY_CONCURRENCY_TEST_ADMIN_URL,
    reason=(
        "Postgres-only real-concurrency test — set "
        "REFRESH_FAMILY_CONCURRENCY_TEST_ADMIN_URL (admin DSN, e.g. "
        "postgresql+psycopg://postgres:pass@localhost:5436/postgres) to run. "
        "Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def pg_engine():
    admin_engine = sa.create_engine(
        REFRESH_FAMILY_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT",
    )
    db_name = f"resort_os_refresh_conctest_{uuid.uuid4().hex[:10]}"
    base_url = REFRESH_FAMILY_CONCURRENCY_TEST_ADMIN_URL.rsplit("/", 1)[0]
    target_url = f"{base_url}/{db_name}"

    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    from app.core.database import Base
    import app.core.kernel.models.user      # noqa: F401
    import app.modules.core.models          # noqa: F401

    engine = sa.create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)

    try:
        yield engine
    finally:
        engine.dispose()
        cleanup_engine = sa.create_engine(
            REFRESH_FAMILY_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT",
        )
        with cleanup_engine.connect() as conn:
            conn.execute(sa.text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
            ))
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        cleanup_engine.dispose()


@pytest.fixture
def Session(pg_engine):
    return sessionmaker(bind=pg_engine, autoflush=False, autocommit=False)


def _make_user(db):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    # A non-mandatory-2FA role so refresh is always allowed regardless of
    # LOGIN_2FA_ENFORCED in the ambient test settings.
    user = User(
        email=f"refresh-{uuid.uuid4().hex[:8]}@conctest.local",
        password_hash=get_password_hash("Test@12345"),
        full_name="Refresh Family Tester", role="manager", is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user.id


def _auth(db):
    from app.core.kernel.auth.service import AuthService
    from app.core.config import settings as app_settings
    from app.core.kernel.models.user import User
    return AuthService(db, User, app_settings)


def _usable_token_count(Session, user_id):
    """Rows that could still be rotated: live successors (not consumed, not
    revoked, not expired)."""
    from app.core.kernel.models.user import RefreshToken
    db = Session()
    try:
        return (
            db.query(RefreshToken)
            .filter(
                RefreshToken.user_id == user_id,
                RefreshToken.consumed_at.is_(None),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
            .count()
        )
    finally:
        db.close()


class TestRefreshRotationRealLock:
    def test_two_concurrent_refreshes_of_same_token_never_double_mint(self, Session):
        """Brief slice B point 1/2: one token, two concurrent rotations
        (threading.Barrier so both start together). The core invariant is that
        the conditional UPDATE NEVER lets both mint a successor — at most one
        successor is ever created.

        Two valid outcomes depend on the exact interleaving, both acceptable
        (and both leave at most one usable token — never two):
          * benign race: both SELECT the row unconsumed, one wins the UPDATE
            and mints the successor, the loser observes zero rows and is
            rejected without revoking the family → 1 usable token remains.
          * staggered: the winner commits its consume before the loser's
            SELECT, so the loser sees the tombstone and treats it as a proven
            replay → the family is revoked → 0 usable tokens remain. This is
            the deliberately security-first trade-off documented in the brief
            (the frontend single-flights refresh, so a single tab never hits
            this; a rare cross-tab simultaneous expiry re-logs in cleanly)."""
        setup = Session()
        user_id = _make_user(setup)
        raw_token = _auth(setup).create_refresh_token(user_id)
        setup.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _rotate(key):
            db = Session()
            try:
                barrier.wait(timeout=5)
                outcome[key] = _auth(db).rotate_refresh_token(raw_token)
            finally:
                db.close()

        t1 = threading.Thread(target=_rotate, args=("t1",))
        t2 = threading.Thread(target=_rotate, args=("t2",))
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive(), "a rotation thread hung"

        succeeded = [v for v in outcome.values() if v is not None]
        # Never a double-mint: at most one successor was ever created.
        assert len(succeeded) <= 1, f"two successors minted — outcome={outcome}"
        # And never two live tokens: either the benign 1, or 0 if the race
        # resolved as a replay that revoked the family.
        assert _usable_token_count(Session, user_id) <= 1

    def test_proven_replay_revokes_whole_family(self, Session):
        """Brief slice B point 3: a consumed token presented again is a
        provable replay → the entire family is revoked, leaving no usable
        successor."""
        setup = Session()
        user_id = _make_user(setup)
        raw_token = _auth(setup).create_refresh_token(user_id)
        setup.close()

        db1 = Session()
        first = _auth(db1).rotate_refresh_token(raw_token)
        db1.close()
        assert first is not None
        _user, successor = first
        assert _usable_token_count(Session, user_id) == 1

        # Replay the consumed parent.
        db2 = Session()
        replay = _auth(db2).rotate_refresh_token(raw_token)
        db2.close()
        assert replay is None

        # Family fully revoked — the once-valid successor is now dead too.
        assert _usable_token_count(Session, user_id) == 0
        db3 = Session()
        assert _auth(db3).rotate_refresh_token(successor) is None
        db3.close()

    def test_use_successor_racing_reuse_parent_is_fail_closed(self, Session):
        """Brief slice B / concurrency point 3: one thread legitimately
        rotates the live successor while another replays the consumed parent.
        Whatever the interleaving, the replay revokes the family, so NO usable
        token can remain — fail-closed."""
        setup = Session()
        user_id = _make_user(setup)
        raw_token = _auth(setup).create_refresh_token(user_id)
        setup.close()

        db0 = Session()
        _user, successor = _auth(db0).rotate_refresh_token(raw_token)
        db0.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _use_successor():
            db = Session()
            try:
                barrier.wait(timeout=5)
                outcome["successor"] = _auth(db).rotate_refresh_token(successor)
            finally:
                db.close()

        def _replay_parent():
            db = Session()
            try:
                barrier.wait(timeout=5)
                outcome["replay"] = _auth(db).rotate_refresh_token(raw_token)
            finally:
                db.close()

        t1 = threading.Thread(target=_use_successor)
        t2 = threading.Thread(target=_replay_parent)
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive(), "a thread hung"

        # The replay of the consumed parent always reports invalid (None)...
        assert outcome["replay"] is None
        # ...and regardless of ordering, the family is revoked: no live token.
        assert _usable_token_count(Session, user_id) == 0

    def test_session_revoke_racing_refresh_does_not_revive_session(self, Session):
        """Brief concurrency point 4: revoking a session concurrently with a
        refresh of that same family must never leave a usable successor
        behind — the revoke wins the family either immediately or by revoking
        the just-minted successor."""
        setup = Session()
        user_id = _make_user(setup)
        auth0 = _auth(setup)
        raw_token = auth0.create_refresh_token(user_id)
        session_ref = auth0.current_session(raw_token)[1]
        setup.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _revoke():
            db = Session()
            try:
                barrier.wait(timeout=5)
                outcome["revoke"] = _auth(db).revoke_session_by_ref(user_id, session_ref)
            finally:
                db.close()

        def _refresh():
            db = Session()
            try:
                barrier.wait(timeout=5)
                outcome["refresh"] = _auth(db).rotate_refresh_token(raw_token)
            finally:
                db.close()

        t1 = threading.Thread(target=_revoke)
        t2 = threading.Thread(target=_refresh)
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive(), "a thread hung"

        # Whatever the ordering, the session is not revived: no usable token.
        assert _usable_token_count(Session, user_id) == 0
