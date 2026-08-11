"""
tests/test_owner_allocation_rule_concurrency.py
Postgres-only real-concurrency proof for the OwnerAllocationRule version-
race fix (2026-08-11). crud.create_allocation_rule_draft used to compute
`MAX(version) + 1` with no locking — SQLite ignores with_for_update
entirely (CLAUDE.md §13 bullet ⓫), so the regular SQLite-backed suite can
only prove the arithmetic, not genuine lock contention between two
concurrent draft-creation requests for the same branch. This file proves
the real thing against a live Postgres, mirroring
tests/test_crm_loyalty_concurrency.py's pattern exactly.

Usage — set an admin Postgres DSN before running:

    OWNER_ALLOC_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://postgres:resort_dev_pass@localhost:5436/postgres \\
        pytest tests/test_owner_allocation_rule_concurrency.py -v

Skips automatically (does not fail, does not affect `pytest tests/`'s
100%-green requirement) when that env var is unset.
"""
from __future__ import annotations

import os
import threading
import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

OWNER_ALLOC_CONCURRENCY_TEST_ADMIN_URL = os.environ.get("OWNER_ALLOC_CONCURRENCY_TEST_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not OWNER_ALLOC_CONCURRENCY_TEST_ADMIN_URL,
    reason=(
        "Postgres-only real-concurrency test — set OWNER_ALLOC_CONCURRENCY_TEST_ADMIN_URL "
        "(admin DSN, e.g. postgresql+psycopg://postgres:pass@localhost:5436/postgres) "
        "to run. Skipped by default; does not affect `pytest tests/`."
    ),
)


@pytest.fixture
def pg_engine():
    admin_engine = sa.create_engine(OWNER_ALLOC_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
    db_name = f"resort_os_owner_alloc_conctest_{uuid.uuid4().hex[:10]}"
    base_url = OWNER_ALLOC_CONCURRENCY_TEST_ADMIN_URL.rsplit("/", 1)[0]
    target_url = f"{base_url}/{db_name}"

    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    from app.core.database import Base
    import app.core.kernel.models.user      # noqa: F401
    import app.modules.core.models          # noqa: F401
    import app.modules.owner.models         # noqa: F401

    engine = sa.create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)

    try:
        yield engine
    finally:
        engine.dispose()
        cleanup_engine = sa.create_engine(OWNER_ALLOC_CONCURRENCY_TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")
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


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Alloc Concurrency Test Branch", name_ar="فرع اختبار تزامن التخصيص",
               code=f"ALLOCCONC-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


class TestAllocationRuleVersionRace:
    def test_two_real_concurrent_drafts_never_collide_on_version(self, Session):
        """فرع واحد، طلبين متزامنين حقيقيين لإنشاء مسودة تخصيص — لازم
        الاتنين ينجحوا (create_draft مفيهاش سبب رفض تجاري يمنع مسودتين)،
        لكن بـversion مختلف تمامًا لكل واحدة (2 و3 مثلاً، بغض النظر عن
        الترتيب) — نفس version لصفين في نفس الفرع يبقى lost update حقيقي
        أو انتهاك للـunique constraint الجديد."""
        from app.modules.owner import services
        from app.modules.owner.schemas import AllocationRuleDraftCreate

        setup_db = Session()
        branch = make_branch(setup_db)
        branch_id = branch.id
        # مسودة أولى موجودة بالفعل (version=1) — عشان نتأكد إن الـMAX+1
        # بيتحسب صح مش بس أول مرة (صف فعلي يتقفل بـFOR UPDATE).
        services.create_draft(
            setup_db,
            AllocationRuleDraftCreate(branch_id=branch_id, pct_rooms=Decimal("10")),
            owner_user_id=1,
        )
        setup_db.close()

        results: list[tuple[str, object]] = []
        start_barrier = threading.Barrier(2)

        def _attempt():
            db = Session()
            try:
                start_barrier.wait(timeout=5)
                rule = services.create_draft(
                    db,
                    AllocationRuleDraftCreate(branch_id=branch_id, pct_beach=Decimal("20")),
                    owner_user_id=1,
                )
                results.append(("ok", rule.version))
            except Exception as exc:  # noqa: BLE001 — أي استثناء لازم يظهر صراحةً، مش يختفي كـ thread crash صامت
                db.rollback()
                results.append(("error", exc))
            finally:
                db.close()

        threads = [threading.Thread(target=_attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
            assert not t.is_alive(), "thread علق (hang حقيقي — القفل ماترفعش صح)"

        oks = [v for kind, v in results if kind == "ok"]
        assert len(oks) == 2, f"لازم الاتنين ينجحوا (مفيش سبب رفض تجاري)، الموجود: {results}"
        assert sorted(oks) == [2, 3], (
            f"لازم version مختلف تمامًا لكل مسودة (2 و3) — تصادم/تكرار "
            f"يعني الـFOR UPDATE lock أو الـunique constraint مش شغالين: {oks}"
        )

        verify_db = Session()
        try:
            from app.modules.owner.models import OwnerAllocationRule
            rows = (
                verify_db.query(OwnerAllocationRule)
                .filter(OwnerAllocationRule.branch_id == branch_id)
                .all()
            )
            versions = sorted(r.version for r in rows)
            assert versions == [1, 2, 3], f"لازم 3 صفوف بversion فريد لكل واحد: {versions}"
        finally:
            verify_db.close()
