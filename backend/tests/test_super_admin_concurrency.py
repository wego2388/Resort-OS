"""
tests/test_super_admin_concurrency.py
Postgres-only real-concurrency proof for Gate 2A's super_admin invariants
(docs/decisions/0003-super-admin-control-plane.md, docs/audits/
gate-2a-super-admin-invariants.md). Row-level locking (SELECT ... FOR
UPDATE on the active-super_admin set + target row, blocking not NOWAIT)
only actually serializes concurrent transactions under a real Postgres
engine — SQLite ignores with_for_update entirely (CLAUDE.md §13 bullet ⓫),
so tests/test_api/test_super_admin_invariants.py can only prove the
exception-handling *contract* deterministically (single-threaded, one
session forcing the pre-condition), not genuine lock contention across
two real overlapping transactions.

Mirrors tests/test_dining_paid_concurrency.py's pattern exactly: an admin
connection creates a disposable, per-test throwaway database (never the
shared dev `resort_os` database), tables are built directly via
Base.metadata.create_all() (no Alembic needed — we're not testing
migration correctness, just row locks), and the database is dropped at the
end regardless of outcome.

Usage — set an admin Postgres DSN before running:

    SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_super_admin_concurrency.py -v

Skips automatically (does not fail, does not affect `pytest tests/`'s
100%-green requirement) when that env var is unset. Deliberately a
**separate** env var from DINING_CONCURRENCY_TEST_ADMIN_URL — different
gate, different throwaway database, per explicit instruction.
"""
from __future__ import annotations

import os
import threading
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL = os.environ.get("SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL,
    reason=(
        "Postgres-only real-concurrency test — set SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL "
        "(admin DSN, e.g. postgresql+psycopg://postgres:pass@localhost:5436/postgres) "
        "to run. Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def pg_engine():
    """نفس نمط tests/test_dining_paid_concurrency.py's pg_engine بالظبط —
    قاعدة بيانات مؤقتة معزولة لكل تست، جداولها متبنية مباشرة، وبتتمسح في
    النهاية دايمًا حتى لو التست فشل."""
    admin_engine = sa.create_engine(SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
    db_name = f"resort_os_superadmin_conctest_{uuid.uuid4().hex[:10]}"
    base_url = SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL.rsplit("/", 1)[0]
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
        cleanup_engine = sa.create_engine(SUPER_ADMIN_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
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


def make_super_admin(db, email_prefix: str):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    user = User(
        email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@conctest.local",
        password_hash=get_password_hash("Test@12345"),
        full_name=f"Super Admin {email_prefix}", role="super_admin", is_active=True,
        two_factor_enabled=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestMutualDemotionRealLock:
    def test_two_active_super_admins_racing_to_demote_each_other_exactly_one_wins(self, Session):
        """السيناريو المطلوب حرفيًا: super_admin نشطان A وB، معاملتان
        متزامنتان (threading.Barrier عشان الاتنين يبدأوا معًا فعليًا) —
        A تحاول تخفّض B، وB تحاول تخفّض A في نفس اللحظة. الترتيب الثابت
        (ORDER BY id) في lock_active_super_admins() يمنع deadlock ويسلسل
        الاتنين بدل ما يتعارضوا. المضمون رياضيًا (راجع خطة Gate 2A):
        المعاملة اللي تاخد القفل الأول تنجح (تفحص العدّاد وقتها = 2،
        مسموح)، والتانية بعد ما تتحرر (تعيد الاستعلام من الصفر) تكتشف إن
        actor بتاعها بقى مش super_admin نشط (اتخفّض بالفعل من التانية) —
        فتترفض بـActorSuperAdminPrivilegesChangedError. النتيجة النهائية
        الوحيدة المقبولة: نجاح واحد بالظبط، ورفض واحد بالظبط (بسبب
        الحماية أو تغيّر صلاحية actor — الاتنين مقبولان زي ما حدد محمد)،
        وsuper_admin نشط واحد بالظبط يفضل في النهاية."""
        from app.modules.core import services as core_services

        setup_db = Session()
        user_a = make_super_admin(setup_db, "mutual-a")
        user_b = make_super_admin(setup_db, "mutual-b")
        a_id, b_id = user_a.id, user_b.id
        setup_db.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _demote(actor_id, target_id, key):
            db = Session()
            try:
                barrier.wait(timeout=5)
                core_services.update_user_role(
                    db, target_id, role="manager", is_active=None, updated_by=actor_id,
                )
                outcome[key] = ("ok", None)
            except Exception as exc:  # noqa: BLE001 — نلتقط أي استثناء للفحص بعدين
                db.rollback()
                outcome[key] = ("error", exc)
            finally:
                db.close()

        t1 = threading.Thread(target=_demote, args=(a_id, b_id, "a_demotes_b"))
        t2 = threading.Thread(target=_demote, args=(b_id, a_id, "b_demotes_a"))
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive(), (
            "thread واحد على الأقل لسه شغال بعد المهلة (hang حقيقي أو "
            f"deadlock) — a_demotes_b done={not t1.is_alive()}, "
            f"b_demotes_a done={not t2.is_alive()}"
        )

        assert "a_demotes_b" in outcome and "b_demotes_a" in outcome, (
            f"نتيجة مفقودة من thread — outcome keys={list(outcome.keys())}"
        )

        kinds = [outcome["a_demotes_b"][0], outcome["b_demotes_a"][0]]
        assert kinds.count("ok") == 1, (
            f"لازم معاملة واحدة بالظبط تنجح، مش {kinds.count('ok')} — outcome={outcome}"
        )
        assert kinds.count("error") == 1

        loser_key = "a_demotes_b" if outcome["a_demotes_b"][0] == "error" else "b_demotes_a"
        loser_exc = outcome[loser_key][1]
        assert isinstance(loser_exc, (
            core_services.ActorSuperAdminPrivilegesChangedError,
            core_services.LastActiveSuperAdminRequiredError,
        )), f"المعاملة الخاسرة اترفضت بسبب غير متوقع: {loser_exc!r}"

        verify_db = Session()
        try:
            from app.core.kernel.models.user import User
            active_super_admins = (
                verify_db.query(User)
                .filter(User.role == "super_admin", User.is_active.is_(True))
                .all()
            )
            assert len(active_super_admins) == 1, (
                f"لازم يفضل super_admin نشط واحد بالظبط، مش {len(active_super_admins)} — "
                "ده بالظبط الغرض من الحماية دي (Decision 0003 invariant #4)"
            )
        finally:
            verify_db.close()

    def test_third_super_admin_can_still_demote_either_after_the_race(self, Session):
        """تأكيد إضافي إن المعاملة الخاسرة معندهاش أي أثر جانبي دائم يمنع
        عمليات لاحقة صحيحة — super_admin تالت (خارج السباق) يقدر يدير
        النظام عاديًا بعد ما السباق يخلص، وإن الفائز الحقيقي من السباق (لسه
        super_admin نشط) هو المستهدَف صح، مش الحساب اللي اتخفّض بالفعل
        (تصحيح مراجعة Codex 2026-07-18: النسخة الأولى كانت بتختار
        still_super_admin_id بشرط معكوس — لو "y" (B تخفّض A) نجحت، كانت
        بتختار a_id رغم إن A هو اللي اتخفّض فعلاً، فـupdate_user_role
        كانت بتتنفّذ كـno-op حقيقي (role="manager" أصلاً) وتنجح من غير ما
        تختبر حاجة فعليًا)."""
        from app.modules.core import services as core_services

        setup_db = Session()
        user_a = make_super_admin(setup_db, "post-race-a")
        user_b = make_super_admin(setup_db, "post-race-b")
        user_c = make_super_admin(setup_db, "post-race-c")
        a_id, b_id, c_id = user_a.id, user_b.id, user_c.id
        setup_db.close()

        barrier = threading.Barrier(2)
        outcome = {}

        def _demote(actor_id, target_id, key):
            db = Session()
            try:
                barrier.wait(timeout=5)
                core_services.update_user_role(db, target_id, role="manager", is_active=None, updated_by=actor_id)
                outcome[key] = ("ok", None)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                outcome[key] = ("error", exc)
            finally:
                db.close()

        # x: A (actor) تخفّض B (target) — لو نجحت، الناجي هو A.
        # y: B (actor) تخفّض A (target) — لو نجحت، الناجي هو B.
        t1 = threading.Thread(target=_demote, args=(a_id, b_id, "x"))
        t2 = threading.Thread(target=_demote, args=(b_id, a_id, "y"))
        t1.start(); t2.start()
        t1.join(timeout=15); t2.join(timeout=15)
        assert not t1.is_alive() and not t2.is_alive()

        assert "x" in outcome and "y" in outcome, f"نتيجة مفقودة — outcome={outcome}"
        kinds = [outcome["x"][0], outcome["y"][0]]
        assert kinds.count("ok") == 1, f"لازم معاملة واحدة بالظبط تنجح — outcome={outcome}"
        assert kinds.count("error") == 1

        loser_key = "x" if outcome["x"][0] == "error" else "y"
        loser_exc = outcome[loser_key][1]
        assert isinstance(loser_exc, (
            core_services.ActorSuperAdminPrivilegesChangedError,
            core_services.LastActiveSuperAdminRequiredError,
        )), f"المعاملة الخاسرة اترفضت بسبب غير متوقع: {loser_exc!r}"

        # اختيار الناجي الصحيح: x نجحت → A لسه super_admin (خفّض B).
        # y نجحت → B لسه super_admin (خفّض A).
        still_super_admin_id = a_id if outcome["x"][0] == "ok" else b_id

        # C (خارج السباق تمامًا) يقدر يخفّض الناجي الحقيقي عادي — ده اختبار
        # حقيقي (role بيتغيّر فعليًا من super_admin لـmanager)، مش no-op.
        after_db = Session()
        try:
            result = core_services.update_user_role(
                after_db, still_super_admin_id, role="manager", is_active=None, updated_by=c_id,
            )
            assert result.role == "manager"
        finally:
            after_db.close()

        verify_db = Session()
        try:
            from app.core.kernel.models.user import User
            active_super_admins = (
                verify_db.query(User)
                .filter(User.role == "super_admin", User.is_active.is_(True))
                .all()
            )
            assert {u.id for u in active_super_admins} == {c_id}, (
                f"لازم يفضل super_admin نشط واحد بس، وهو C — النتيجة الفعلية: "
                f"{[u.id for u in active_super_admins]}"
            )
        finally:
            verify_db.close()
