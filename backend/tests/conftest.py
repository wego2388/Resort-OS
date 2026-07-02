"""
tests/conftest.py
═══════════════════════════════════════════════════════════════════════
إعداد بيئة الاختبار الكاملة

الاستخدام:
    pytest tests/                          # الكل
    pytest tests/test_engines/ -v          # Engines فقط (سريع، بدون DB)
    pytest tests/test_api/ -v              # Integration مع SQLite in-memory
    pytest tests/ --cov=app --cov-report=term-missing

متغيرات البيئة المطلوبة (أو تُحدَّد تلقائياً هنا):
    DATABASE_URL    → sqlite:///./test.db (يُعيَّن تلقائياً)
    SECRET_KEY      → test-secret-key-minimum-32-chars (يُعيَّن تلقائياً)
    REDIS_URL       → fakeredis (يُعيَّن تلقائياً)
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Generator

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# ─── إعداد متغيرات البيئة قبل أي import من app ───────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-chars-here-xxxx")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6381/0")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("CELERY_TASK_EAGER_PROPAGATES", "true")
os.environ.setdefault("RESORT_NAME", "Test Resort")
os.environ.setdefault("DEFAULT_CURRENCY", "EGP")
os.environ.setdefault("VAT_PERCENTAGE", "14.0")
os.environ.setdefault("SERVICE_CHARGE_PERCENTAGE", "12.0")
os.environ.setdefault("TIMEZONE", "Africa/Cairo")
os.environ.setdefault("ETA_ENABLED", "false")
os.environ.setdefault("SURVEY_TOKEN_SECRET", "test-survey-secret-minimum-32-chars-xx")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", "9g2Hqbw0QQod3CiEaA9MMrWBpXmb3J3Hb6MEdwv2FeQ=")

# ─── SQLite In-Memory Engine ──────────────────────────────────────────

SQLALCHEMY_TEST_DATABASE_URL = "sqlite://"  # in-memory

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # نفس الـ connection لكل الـ threads في test
)

# تفعيل FK enforcement في SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ─── إنشاء الجداول ────────────────────────────────────────────────────

def create_all_tables() -> None:
    """ينشئ كل الجداول في SQLite in-memory."""
    from app.core.database import Base  # noqa: PLC0415
    import wego_core.models.user           # noqa: F401, PLC0415 — users/refresh_tokens/token_blacklist
    import app.modules.core.models         # noqa: F401, PLC0415
    import app.modules.finance.models      # noqa: F401, PLC0415
    import app.modules.hr.models           # noqa: F401, PLC0415
    import app.modules.restaurant.models   # noqa: F401, PLC0415
    import app.modules.pms.models          # noqa: F401, PLC0415
    import app.modules.beach.models        # noqa: F401, PLC0415
    import app.modules.maintenance.models  # noqa: F401, PLC0415
    import app.modules.crm.models          # noqa: F401, PLC0415
    import app.modules.hub.models          # noqa: F401, PLC0415
    import app.modules.inventory.models    # noqa: F401, PLC0415
    import app.modules.timeshare.models    # noqa: F401, PLC0415
    import app.modules.leasing.models      # noqa: F401, PLC0415
    import app.modules.cafe.models         # noqa: F401, PLC0415
    import app.modules.analytics.models    # noqa: F401, PLC0415
    Base.metadata.create_all(bind=engine)


# ─── get_test_db ──────────────────────────────────────────────────────

def get_test_db() -> Generator[Session, None, None]:
    """Generator يُعيد Session ويعمل rollback بعد الاستخدام."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


# ─── Fake Redis ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fake_redis():
    """fakeredis server — لا يحتاج Redis حقيقي."""
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server)
    return client


# ─── DB Fixture ───────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """ينشئ الجداول مرة واحدة لكل session."""
    create_all_tables()
    yield
    # نظّف بعد كل tests
    from app.core.database import Base  # noqa: PLC0415
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db(setup_db) -> Generator[Session, None, None]:
    """
    DB session نظيفة لكل test — rollback بعد الانتهاء.
    كل test تبدأ بـ DB فارغة.
    """
    yield from get_test_db()


# ─── App & TestClient ─────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app(fake_redis):
    """FastAPI app مهيّأة للاختبار."""
    from app.main import create_app  # noqa: PLC0415
    from app.core.deps import get_db, get_redis  # noqa: PLC0415

    application = create_app()

    # Override dependencies
    def _override_get_db():
        yield from get_test_db()

    def _override_get_redis():
        return fake_redis

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_redis] = _override_get_redis

    return application


@pytest.fixture(scope="session")
def client(app) -> TestClient:
    """HTTP client للـ integration tests."""
    with TestClient(app) as c:
        yield c


# ─── Auth Helpers ─────────────────────────────────────────────────────
#
# ⚠️ get_current_user يعمل DB lookup حقيقي بالـ email (sub claim) — مش
# بيثق في role/level claims جوه التوكن. فأي fixture هنا لازم تعمل commit
# لصف User حقيقي في نفس الـ DB اللي الـ app fixture بتستخدمها (get_test_db)،
# مش بس تولّد توكن بادعاءات. راجع CLAUDE.md § 5 لتفاصيل الـ gotcha ده.

def _make_token(email: str) -> str:
    """ينشئ JWT token متوافق مع get_current_user — sub=email + iat حقيقي."""
    from jose import jwt  # noqa: PLC0415
    secret = os.environ["SECRET_KEY"]
    now = datetime.utcnow()
    payload = {"sub": email, "iat": now, "exp": now + timedelta(hours=1)}
    return jwt.encode(payload, secret, algorithm="HS256")


def _create_test_user(email: str, role: str, two_factor_enabled: bool = False):
    """ينشئ (أو يرجّع الموجود) صف User حقيقي — يُستخدم من fixtures الـ headers."""
    from wego_core.models.user import User  # noqa: PLC0415
    from wego_core.security import get_password_hash  # noqa: PLC0415

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email, password_hash=get_password_hash("Test@12345"),
                full_name=f"Test {role}", role=role, is_active=True,
                two_factor_enabled=two_factor_enabled,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user.id
    finally:
        db.close()


@pytest.fixture
def super_admin_headers(setup_db) -> dict[str, str]:
    # super_admin لازم 2FA (MANDATORY_2FA_ROLES) — نعتبره مفعّل مسبقاً للاختبار
    _create_test_user("super_admin@test.local", "super_admin", two_factor_enabled=True)
    return {"Authorization": f"Bearer {_make_token('super_admin@test.local')}"}


@pytest.fixture
def manager_headers(setup_db) -> dict[str, str]:
    _create_test_user("manager@test.local", "manager")
    return {"Authorization": f"Bearer {_make_token('manager@test.local')}"}


@pytest.fixture
def cashier_headers(setup_db) -> dict[str, str]:
    _create_test_user("cashier@test.local", "cashier")
    return {"Authorization": f"Bearer {_make_token('cashier@test.local')}"}


@pytest.fixture
def waiter_headers(setup_db) -> dict[str, str]:
    _create_test_user("waiter@test.local", "waiter")
    return {"Authorization": f"Bearer {_make_token('waiter@test.local')}"}


# ─── Sample Data Fixtures ─────────────────────────────────────────────

@pytest.fixture
def sample_branch(db: Session):
    """فرع اختباري."""
    from app.modules.core.models import Branch  # noqa: PLC0415
    branch = Branch(
        name="Test Branch",
        name_ar="الفرع الاختباري",
        code="TST-001",
        gm_phone="+201000000000",
    )
    db.add(branch)
    db.flush()
    return branch


@pytest.fixture
def sample_room(db: Session, sample_branch):
    """غرفة اختبارية — تتطلب PMS models."""
    try:
        from app.modules.pms.models import Room, RoomType  # noqa: PLC0415
        room_type = RoomType(
            branch_id=sample_branch.id,
            name="Standard Room",
            name_ar="غرفة عادية",
            base_rate=Decimal("500.00"),
            max_occupancy=2,
        )
        db.add(room_type)
        db.flush()
        room = Room(
            branch_id=sample_branch.id,
            room_type_id=room_type.id,
            name="101",
            floor=1,
            status="available",
        )
        db.add(room)
        db.flush()
        return room
    except ImportError:
        pytest.skip("PMS module not implemented yet")


@pytest.fixture
def sample_product(db: Session, sample_branch):
    """منتج اختباري — تتطلب Restaurant models."""
    try:
        from app.modules.restaurant.models import MenuItem  # noqa: PLC0415
        item = MenuItem(
            branch_id=sample_branch.id,
            name="Test Item",
            name_ar="صنف اختباري",
            price=Decimal("50.00"),
            is_available=True,
        )
        db.add(item)
        db.flush()
        return item
    except ImportError:
        pytest.skip("Restaurant module not implemented yet")


@pytest.fixture
def sample_booking(db: Session, sample_branch, sample_room):
    """حجز اختباري."""
    try:
        from app.modules.pms.models import Booking, Folio  # noqa: PLC0415
        folio = Folio(branch_id=sample_branch.id, status="open", total=Decimal("0"))
        db.add(folio)
        db.flush()
        booking = Booking(
            branch_id=sample_branch.id,
            folio_id=folio.id,
            guest_name="Test Guest",
            check_in=date.today(),
            check_out=date.today() + timedelta(days=2),
            status="confirmed",
            adults=1,
            children=0,
        )
        db.add(booking)
        db.flush()
        return booking
    except ImportError:
        pytest.skip("PMS module not implemented yet")


# ─── Celery Eager Mode ────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def celery_eager_mode():
    """
    يجعل Celery tasks تعمل synchronously في الاختبارات.
    لا worker خارجي مطلوب.
    """
    try:
        from app.core.celery_app import celery_app  # noqa: PLC0415
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True
        yield
        celery_app.conf.task_always_eager = False
    except ImportError:
        yield  # Celery غير موجود بعد — تجاهل


# ─── Module Toggle Helper ─────────────────────────────────────────────
#
# Several modules default to `default_enabled=False` in MODULE_REGISTRY
# (beach, pms, timeshare, leasing, crm, hub — see app/core/module_loader.py).
# HTTP-level tests go through the real `require_module()` dependency, so a
# freshly-created Branch with no ModuleState row will 403 with MODULE_DISABLED
# on any of those modules' endpoints. Service-level tests never hit this
# because they call services.xxx() directly, bypassing the router entirely.
# Use this helper (committed, not flushed) to enable a module for a branch
# (or globally if branch_id=None) before exercising its HTTP endpoints.
#
# ⚠️ is_module_enabled() caches the FULL enabled-module SET per branch_id in
# Redis for 60s (module_loader.CACHE_TTL). Since `fake_redis` is a
# session-scoped fixture shared by every test in the run, an earlier test
# (e.g. one exercising the beach module) can poison the cache for a later
# test (e.g. pms) within the same 60s window — the cached snapshot simply
# won't have "pms" in its enabled set yet. That's why this helper takes the
# `fake_redis` client explicitly and flushes it after every DB write, so the
# very next request always recomputes the enabled-set fresh from DB.

def enable_module_for_branch(db, fake_redis, module_key: str, branch_id: int | None = None) -> None:
    from app.modules.core.models import ModuleState  # noqa: PLC0415

    existing = (
        db.query(ModuleState)
        .filter(ModuleState.module_key == module_key, ModuleState.branch_id == branch_id)
        .first()
    )
    if existing:
        existing.enabled = True
    else:
        db.add(ModuleState(module_key=module_key, enabled=True, branch_id=branch_id))
    db.commit()
    fake_redis.flushall()


# ─── Discount Engine Test Helpers ────────────────────────────────────

@pytest.fixture
def discount_factory(db: Session, sample_branch):
    """Factory لإنشاء discounts في الاختبارات."""
    from app.resort_os.discount_engine import ConditionalDiscount  # noqa: PLC0415

    def _create(
        condition_type: str = "total_amount",
        condition_value: str = ">=100",
        discount_type: str = "percentage",
        discount_value: Decimal = Decimal("10"),
        priority: int = 1,
        valid_from: date | None = None,
        valid_until: date | None = None,
    ) -> ConditionalDiscount:
        discount = ConditionalDiscount(
            branch_id=sample_branch.id,
            condition_type=condition_type,
            condition_value=condition_value,
            discount_type=discount_type,
            discount_value=discount_value,
            max_uses=-1,
            valid_from=valid_from or date.today(),
            valid_until=valid_until or (date.today() + timedelta(days=365)),
            priority=priority,
        )
        db.add(discount)
        db.flush()
        return discount

    return _create
