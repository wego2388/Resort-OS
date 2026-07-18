"""
tests/test_step_up_concurrency.py
Postgres-only real-concurrency proof for Gate 2B3A's step-up consumption —
docs/decisions/0003-super-admin-control-plane.md follow-up,
docs/audits/gate-2b3a-step-up-control-plane.md.

AuthService.consume_step_up()'s atomicity claim ("exactly one of two
concurrent requests against the same proof can succeed") rests entirely on
a single conditional DELETE's own affected-row-count — that guarantee only
means anything under a real Postgres engine with real concurrent
transactions; SQLite has no meaningful concurrent-transaction story (single
writer, whole-database lock), so tests/test_api/test_step_up_control_plane.py
can only prove the *contract* deterministically (one thread, sequential
calls), not genuine race-condition safety.

Mirrors tests/test_super_admin_concurrency.py's pattern exactly: an admin
connection creates a disposable, per-test throwaway database, tables are
built directly via Base.metadata.create_all() (no Alembic needed — this is
about the DELETE's row-count semantics, not migration correctness), and the
database is dropped at the end regardless of outcome.

Usage — set an admin Postgres DSN before running:

    STEP_UP_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_step_up_concurrency.py -v

Skips automatically (does not fail, does not affect `pytest tests/`'s
100%-green requirement) when that env var is unset. Deliberately a
**separate** env var from SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL/
DINING_CONCURRENCY_TEST_ADMIN_URL — different gate, different throwaway
database.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

STEP_UP_CONCURRENCY_TEST_ADMIN_URL = os.environ.get("STEP_UP_CONCURRENCY_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not STEP_UP_CONCURRENCY_TEST_ADMIN_URL,
    reason=(
        "Postgres-only real-concurrency test — set STEP_UP_CONCURRENCY_TEST_ADMIN_URL "
        "(admin DSN, e.g. postgresql+psycopg://postgres:pass@localhost:5436/postgres) "
        "to run. Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def pg_engine():
    """نفس نمط tests/test_super_admin_concurrency.py's pg_engine بالظبط —
    قاعدة بيانات مؤقتة معزولة لكل تست، جداولها متبنية مباشرة، وبتتمسح في
    النهاية دايمًا حتى لو التست فشل."""
    admin_engine = sa.create_engine(STEP_UP_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
    db_name = f"resort_os_stepup_conctest_{uuid.uuid4().hex[:10]}"
    base_url = STEP_UP_CONCURRENCY_TEST_ADMIN_URL.rsplit("/", 1)[0]
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
        cleanup_engine = sa.create_engine(STEP_UP_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
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


def make_user(db, email_prefix: str, role: str = "super_admin"):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    user = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@conctest.local",
        password_hash=get_password_hash("Test@12345"),
        full_name=f"User {email_prefix}", role=role, is_active=True,
        two_factor_enabled=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_grant(db, *, user_id: int, token_hash: str, access_token_hash: str,
                purpose: str, scope_hash: str):
    from app.core.kernel.models.user import StepUpGrant
    grant = StepUpGrant(
        public_reference=uuid.uuid4().hex[:16],
        user_id=user_id, purpose=purpose, scope_hash=scope_hash,
        token_hash=token_hash, access_token_hash=access_token_hash,
        assurance_method="totp",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=180),
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant


class TestConsumeStepUpRealLock:
    def test_two_concurrent_consumptions_of_same_grant_exactly_one_succeeds(self, Session):
        """السيناريو المطلوب حرفيًا (Part 10 من مواصفة Gate 2B3A): إثبات
        واحد، طلبان متزامنان (threading.Barrier عشان الاتنين يبدأوا معًا
        فعليًا) بنفس التوكن/user_id/purpose/scope_hash/access_token_hash —
        الـDELETE الشرطي في consume_step_up لازم يخلي واحد بالظبط يفوز
        (affected-row-count=1) والتاني يفشل (affected-row-count=0)، من غير
        أي فحص منفصل قبله يقرر النتيجة."""
        from app.core.kernel.auth.service import AuthService
        from app.core.config import settings as app_settings
        from app.core.kernel.models.user import User

        setup_db = Session()
        user = make_user(setup_db, "consume-race")
        user_id = user.id
        raw_token = "race-token-" + uuid.uuid4().hex
        token_hash = AuthService._hash_token(raw_token)
        access_token_hash = AuthService._hash_token("fake-access-token-for-this-session")
        purpose = "user_role_update"
        scope_hash = "a" * 64  # قيمة SHA-256-shaped ثابتة — مش مهم محتواها هنا، بس التطابق
        make_grant(
            setup_db, user_id=user_id, token_hash=token_hash,
            access_token_hash=access_token_hash, purpose=purpose, scope_hash=scope_hash,
        )
        setup_db.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _consume(key):
            db = Session()
            try:
                auth = AuthService(db, User, app_settings)
                barrier.wait(timeout=5)
                result = auth.consume_step_up(
                    user_id=user_id, purpose=purpose, scope_hash=scope_hash,
                    access_token_hash=access_token_hash, token=raw_token,
                )
                outcome[key] = result
            finally:
                db.close()

        t1 = threading.Thread(target=_consume, args=("t1",))
        t2 = threading.Thread(target=_consume, args=("t2",))
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive(), (
            "thread واحد على الأقل لسه شغال بعد المهلة (hang حقيقي) — "
            f"t1 done={not t1.is_alive()}, t2 done={not t2.is_alive()}"
        )

        assert "t1" in outcome and "t2" in outcome, f"نتيجة مفقودة — outcome={outcome}"
        results = [outcome["t1"], outcome["t2"]]
        succeeded = [r for r in results if r is not None]
        failed = [r for r in results if r is None]
        assert len(succeeded) == 1, (
            f"لازم استهلاك واحد بالظبط ينجح، مش {len(succeeded)} — outcome={outcome}"
        )
        assert len(failed) == 1

        verify_db = Session()
        try:
            from app.core.kernel.models.user import StepUpGrant
            remaining = verify_db.query(StepUpGrant).filter(
                StepUpGrant.user_id == user_id,
            ).count()
            assert remaining == 0, "الصف لازم يتحذف نهائيًا بعد أول استهلاك ناجح"
        finally:
            verify_db.close()

    def test_sequential_consumption_after_first_success_always_fails(self, Session):
        """تكملة منطقية للسباق: حتى برا سياق تزامن حقيقي، أي محاولة استهلاك
        *بعد* نجاح الأولى (مش بالتوازي، بالتتابع) لازم تفشل بردو — الصف
        بقى محذوف فعليًا، مفيش حاجة تفرق."""
        from app.core.kernel.auth.service import AuthService
        from app.core.config import settings as app_settings
        from app.core.kernel.models.user import User

        setup_db = Session()
        user = make_user(setup_db, "consume-seq")
        user_id = user.id
        raw_token = "seq-token-" + uuid.uuid4().hex
        token_hash = AuthService._hash_token(raw_token)
        access_token_hash = AuthService._hash_token("fake-access-token-seq")
        purpose = "setting_upsert"
        scope_hash = "b" * 64
        make_grant(
            setup_db, user_id=user_id, token_hash=token_hash,
            access_token_hash=access_token_hash, purpose=purpose, scope_hash=scope_hash,
        )
        setup_db.close()

        db1 = Session()
        auth1 = AuthService(db1, User, app_settings)
        first = auth1.consume_step_up(
            user_id=user_id, purpose=purpose, scope_hash=scope_hash,
            access_token_hash=access_token_hash, token=raw_token,
        )
        db1.close()
        assert first is not None

        db2 = Session()
        auth2 = AuthService(db2, User, app_settings)
        second = auth2.consume_step_up(
            user_id=user_id, purpose=purpose, scope_hash=scope_hash,
            access_token_hash=access_token_hash, token=raw_token,
        )
        db2.close()
        assert second is None


class TestGrantPermissionActorAndTargetRaceRealLock:
    """مراجعة Codex المستقلة (2026-07-18، High #2): إثبات تزامن حقيقي إن
    ترقية target لـsuper_admin بالتزامن مع منح صلاحية صريحة له مايسيبش
    أي حالة غير آمنة — إما الترقية تفوز بالقفل الأول (grant_permission
    بيرفض SuperAdminPermissionOverrideForbiddenError)، أو المنح يفوز
    (override بيتسجّل، لكن يفضل عديم الأثر تمامًا بمجرد ما target يبقى
    super_admin نشط — Decision 0003 invariant #1، نفس نمط
    test_explicit_deny_stays_inert_for_active_super_admin_real_endpoint
    في test_super_admin_invariants.py). النتيجتان الاتنين آمنتان؛ غير
    المقبول الوحيد هو حالة وسط غير متسقة (deadlock، صف مكرر، إلخ)."""

    def test_promote_target_concurrently_with_grant_permission(self, Session):
        from app.modules.core import services as core_services
        from app.modules.core.schemas import UserPermissionCreate

        setup_db = Session()
        actor = make_user(setup_db, "race-grant-actor", role="super_admin")
        promoter = make_user(setup_db, "race-grant-promoter", role="super_admin")
        target = make_user(setup_db, "race-grant-target", role="waiter")
        actor_id, promoter_id, target_id = actor.id, promoter.id, target.id
        setup_db.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _grant():
            db = Session()
            try:
                barrier.wait(timeout=5)
                perm = core_services.grant_permission(
                    db, target_id,
                    UserPermissionCreate(resource="dining.void_order_item", action="execute", allowed=True),
                    granted_by=actor_id,
                )
                outcome["grant"] = ("ok", perm.id)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                outcome["grant"] = ("error", exc)
            finally:
                db.close()

        def _promote():
            db = Session()
            try:
                barrier.wait(timeout=5)
                core_services.update_user_role(
                    db, target_id, role="super_admin", is_active=None, updated_by=promoter_id,
                )
                outcome["promote"] = ("ok", None)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                outcome["promote"] = ("error", exc)
            finally:
                db.close()

        t1 = threading.Thread(target=_grant)
        t2 = threading.Thread(target=_promote)
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive(), (
            "thread واحد على الأقل لسه شغال بعد المهلة (hang أو deadlock حقيقي) — "
            f"grant done={not t1.is_alive()}, promote done={not t2.is_alive()}"
        )

        assert "grant" in outcome and "promote" in outcome, f"نتيجة مفقودة — outcome={outcome}"
        # الترقية نفسها لازم تنجح دايمًا (مفيش سبب يرفضها هنا — target مش
        # actor، مفيش self-lockout ولا last-active-admin في اللعبة).
        assert outcome["promote"][0] == "ok", f"الترقية اترفضت بشكل غير متوقع: {outcome['promote']}"

        verify_db = Session()
        try:
            from app.core.kernel.models.user import User
            from app.modules.core import crud as core_crud
            final_target = verify_db.query(User).filter(User.id == target_id).first()
            assert final_target.role == "super_admin"

            if outcome["grant"][0] == "ok":
                # المنح فاز بالسباق (نفّذ قبل الترقية) — override موجود،
                # لكن لازم يبقى عديم الأثر تمامًا دلوقتي إن target بقى
                # super_admin نشط.
                from app.modules.core.services import has_permission
                verify_db.refresh(final_target)
                allowed = has_permission(
                    verify_db, final_target, "dining.void_order_item", "execute", role_fallback=True,
                )
                assert allowed is True, "override لازم يبقى عديم الأثر لـsuper_admin نشط"
            else:
                # الترقية فازت بالسباق — grant_permission لازم يكون رفض
                # بالضبط بـSuperAdminPermissionOverrideForbiddenError، مش
                # أي استثناء تاني غامض.
                assert isinstance(
                    outcome["grant"][1], core_services.SuperAdminPermissionOverrideForbiddenError,
                ), f"المنح اترفض بسبب غير متوقع: {outcome['grant'][1]!r}"
                assert core_crud.find_explicit_permission(
                    verify_db, target_id, "dining.void_order_item", "execute",
                ) is None
        finally:
            verify_db.close()
