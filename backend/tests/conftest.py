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
    import app.core.kernel.models.user           # noqa: F401, PLC0415 — users/refresh_tokens/token_blacklist
    import app.modules.core.models         # noqa: F401, PLC0415
    import app.modules.finance.models      # noqa: F401, PLC0415
    import app.modules.hr.models           # noqa: F401, PLC0415
    import app.modules.pms.models          # noqa: F401, PLC0415
    import app.modules.beach.models        # noqa: F401, PLC0415
    import app.modules.maintenance.models  # noqa: F401, PLC0415
    import app.modules.crm.models          # noqa: F401, PLC0415
    import app.modules.hub.models          # noqa: F401, PLC0415
    import app.modules.inventory.models    # noqa: F401, PLC0415
    import app.modules.timeshare.models    # noqa: F401, PLC0415
    import app.modules.leasing.models      # noqa: F401, PLC0415
    import app.modules.analytics.models    # noqa: F401, PLC0415
    import app.modules.dining.models       # noqa: F401, PLC0415
    Base.metadata.create_all(bind=engine)


def _create_default_test_user() -> None:
    """يضمن وجود user.id == 1 في بيئة الاختبار من أجل مراجع التدقيق التلقائية."""
    from app.core.kernel.models.user import User, UserRole  # noqa: PLC0415
    from app.core.kernel.security import get_password_hash  # noqa: PLC0415

    db = TestingSessionLocal()
    try:
        existing = db.query(User).filter(User.id == 1).first()
        if existing:
            return
        user = User(
            id=1,
            email="system@test.local",
            password_hash=get_password_hash("System@12345"),
            full_name="System User",
            role=UserRole.SUPER_ADMIN,
            is_active=True,
            two_factor_enabled=False,
        )
        db.add(user)
        db.commit()
    finally:
        db.close()


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
#
# ⚠️ باج عزل حقيقي كان هنا: REDIS_URL فوق بيتعمله setdefault على
# redis://localhost:6381/0 — الـ Redis الحقيقي بتاع الديف، مش وهمي. لكن
# app.core.kernel.cache._redis بيتصل بـ redis.from_url(REDIS_URL) وقت
# الـ import (مرة واحدة بس)، وده مش نفس الـ FakeRedis instance اللي فيكستشر
# fake_redis التحت ده كانت بتنشئه — يعني كل تست بيستخدم الـ cache الحقيقية
# (rate_limit/get_cache/set_cache/token revocation) كان فعليًا بيقرا ويكتب
# على الـ Redis الحقيقي، وحالته بتفضل موجودة بين تشغيلة وتانية (وممكن
# تتصادم مع سيرفر ديف شغال فعليًا على نفس البورت). الحل: نعمل monkey-patch
# لـ redis.from_url نفسها *قبل* أول import لـ app.core.kernel.cache في أي
# مكان (السطور دي بتتنفذ أول ما conftest.py يتحمّل، قبل أي test/fixture)،
# فبيرجع نفس الـ fakeredis client اللي fake_redis fixture بترجعه — فـ
# الاتنين (كود التطبيق + التستات اللي بتستخدم فيكستشر fake_redis مباشرة)
# بيشتغلوا على نفس الـ backing store الوهمي، مش حاجتين منفصلتين.
import redis as _redis_module  # noqa: E402

_shared_fake_redis_server = fakeredis.FakeServer()
_shared_fake_redis_client = fakeredis.FakeRedis(
    server=_shared_fake_redis_server, decode_responses=True
)
_redis_module.from_url = lambda *_args, **_kwargs: _shared_fake_redis_client


@pytest.fixture(scope="session")
def fake_redis():
    """نفس الـ fakeredis client اللي app.core.kernel.cache._redis بيتحقن
    بيه فعليًا (راجع المونكي-باتش فوق) — مش instance وهمي منفصل."""
    return _shared_fake_redis_client


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    """⚠️ باج عزل حقيقي كان هنا (اتصلح 2026-07-07، اتكشف لما restaurant/cafe
    public/orders بقوا rate-limited): الـ fake_redis اللي بيغذّي rate_limit()
    فوق session-scoped — بيفضل نفس الـ instance طول الـ test session كلها،
    ومفيش أي تنظيف بينهم. كل التستات بتستخدم نفس TestClient (نفس "IP" فعليًا
    من منظور rate_limit، مهما كان عدد fixtures/تستات مختلفة)، يعني أي
    endpoint اتضاف له rate limit جديد بيتراكم عليه request count من كل
    التستات اللي عدّت قبله في نفس الـ session — لما العدد يعدّي الحد
    (30/60s مثلاً)، تستات شرعية تمامًا بعد كده كانت بترجع 429 بدل النتيجة
    المتوقعة. بيمسح مفاتيح rl:* قبل كل تست عشان كل تست يبدأ بحد ائتمان
    نظيف، بغض النظر عن أي endpoint اتضاف له limit جديد مستقبلاً."""
    for key in _shared_fake_redis_client.keys("rl:*"):
        _shared_fake_redis_client.delete(key)
    yield


@pytest.fixture(autouse=True)
def _reset_gate1_containment_switches():
    """Gate 1 containment (جولة مراجعة Codex الثالثة/الأمنية النهائية):
    DINING_SELF_ORDER_ENABLED/GUEST_ALERTS_ENABLED/RATE_LIMIT_TRUSTED_PROXY_HOPS
    دلوقتي typed settings على الـsingleton `settings` (مش env var لكل تست) —
    لازم يرجعوا لقيمتهم الافتراضية قبل كل تست وبعده، وإلا تست فعّلهم بيسرّب
    الحالة للي بعده. نفس نمط _reset_rate_limit_state فوق بالظبط."""
    from app.core.config import settings
    settings.DINING_SELF_ORDER_ENABLED = False
    settings.GUEST_ALERTS_ENABLED = False
    settings.RATE_LIMIT_TRUSTED_PROXY_HOPS = 0
    settings.PUBLIC_REGISTRATION_ENABLED = False
    yield
    settings.DINING_SELF_ORDER_ENABLED = False
    settings.GUEST_ALERTS_ENABLED = False
    settings.RATE_LIMIT_TRUSTED_PROXY_HOPS = 0
    settings.PUBLIC_REGISTRATION_ENABLED = False


# ─── DB Fixture ───────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """ينشئ الجداول مرة واحدة لكل session."""
    create_all_tables()
    _create_default_test_user()
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
    from app.core.deps import get_db  # noqa: PLC0415

    application = create_app()

    # Override dependencies
    def _override_get_db():
        yield from get_test_db()

    application.dependency_overrides[get_db] = _override_get_db

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


class _FakeLockNotAvailable(Exception):
    """يحاكي psycopg.errors.LockNotAvailable — بس السمة اللي
    app.core.db_errors.is_lock_not_available فعليًا بتتحقق منها
    (``sqlstate``), مش الكلاس نفسه. راجع Gate 1B مراجعة Codex الثانية:
    الكود بقى يميّز PostgreSQL SQLSTATE 55P03 الحقيقي (قفل NOWAIT مشغول)
    عن أي OperationalError تاني (فقدان اتصال، مشكلة سيرفر...) قبل ما
    يحوّله لخطأ تزامن — أي monkeypatch بيحاكي "الصف مشغول" لازم يبني
    OperationalError بنفس الشكل ده، وإلا هيتصعّد كخطأ حقيقي مش يتحول 409."""
    sqlstate = "55P03"


def make_lock_not_available_error(context: str = "SELECT ... FOR UPDATE NOWAIT") -> "OperationalError":
    """OperationalError حقيقي الشكل بيمثّل PostgreSQL lock_not_available —
    استخدمها في monkeypatch بدل ``OperationalError(..., Exception(...))``
    الخام عشان تمر من فحص is_lock_not_available صح."""
    from sqlalchemy.exc import OperationalError  # noqa: PLC0415
    return OperationalError(context, {}, _FakeLockNotAvailable("could not obtain lock"))


def make_unrelated_operational_error(context: str = "connection lost") -> "OperationalError":
    """OperationalError حقيقي الشكل بيمثّل مشكلة قاعدة بيانات **مش** متعلقة
    بقفل صف (فقدان اتصال، مشكلة سيرفر...) — لازم يفضل يتصعّد كخطأ حقيقي،
    مش يتحول لخطأ تزامن 409 مضلّل."""
    from sqlalchemy.exc import OperationalError  # noqa: PLC0415
    return OperationalError(context, {}, Exception("server closed the connection unexpectedly"))


def open_cashier_shift(db, branch_id: int, cashier_id: int, opening_float="0"):
    """Gate 4A test helper: يفتح وردية كاشير مباشرة عبر الـ ORM — بعد Gate 4A
    أي تحصيل دفع مباشر (cash/card/wallet) عبر مسار HTTP (اللي بيمرّر
    settled_by=user.id) بيتطلب وردية مفتوحة لهذا الكاشير والفرع، وإلا 409
    NO_OPEN_SHIFT. أي تست بيدفع طلب دايننج كاش/كارت بهوية كاشير حقيقية لازم
    يفتح وردية الأول (زي الكاشير الحقيقي بالظبط)."""
    from decimal import Decimal  # noqa: PLC0415
    from datetime import datetime  # noqa: PLC0415
    from app.modules.finance.models import CashierShift  # noqa: PLC0415

    existing = (
        db.query(CashierShift)
        .filter(
            CashierShift.branch_id == branch_id,
            CashierShift.cashier_id == cashier_id,
            CashierShift.status == "open",
        )
        .first()
    )
    if existing:
        return existing
    shift = CashierShift(
        branch_id=branch_id, cashier_id=cashier_id,
        opened_at=datetime.utcnow(), opened_by=cashier_id,
        opening_float=Decimal(str(opening_float)), status="open",
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


def ws_url(path: str, headers: dict[str, str]) -> str:
    """يحوّل مسار WebSocket + fixture headers (زي waiter_headers) لرابط فيه
    ?token=... — كل WebSocket endpoint بقى يتطلبه (wagdy.md A-01،
    get_websocket_user في app/core/deps.py). WebSocket API في المتصفح
    مايدعمش custom headers، فالتوكن بيوصل كـ query param بدل Authorization."""
    token = headers["Authorization"].removeprefix("Bearer ")
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}token={token}"


def _create_test_user(
    email: str, role: str, two_factor_enabled: bool = False,
    two_factor_secret: str | None = None,
):
    """ينشئ (أو يرجّع الموجود) صف User حقيقي — يُستخدم من fixtures الـ headers.

    ``two_factor_secret``: سرّ TOTP حقيقي (base32، عادة ``pyotp.random_base32()``)
    — لازم لأي اختبار Gate 2B3A محتاج يصدر step-up token فعلي لحساب مفروض
    عليه 2FA (مجرد ``two_factor_enabled=True`` من غير سرّ حقيقي كافي لتخطي
    get_current_active_user's mandatory-2FA gate، لكن مش كافي لتوليد كود
    TOTP صالح فعليًا)."""
    from app.core.kernel.models.user import User  # noqa: PLC0415
    from app.core.kernel.security import get_password_hash  # noqa: PLC0415

    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email, password_hash=get_password_hash("Test@12345"),
                full_name=f"Test {role}", role=role, is_active=True,
                two_factor_enabled=two_factor_enabled or bool(two_factor_secret),
                two_factor_secret=two_factor_secret,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user.id
    finally:
        db.close()


def _issue_step_up(
    client, headers: dict[str, str], *,
    purpose: str, intent: dict, password: str = "Test@12345",
    totp_secret: str | None = None, recovery_code: str | None = None,
    totp_offset_steps: int = 0,
) -> str:
    """Gate 2B3A: يصدر step_up_token حقيقي عبر POST /auth/step-up — تُستخدم
    من كل اختبار HTTP لأي من الأربعة endpoints المحمية بدل تكرار نفس منطق
    الطلب في كل ملف. ``intent`` لازم يحتوي نفس الحقول بالظبط اللي الـ
    endpoint المُستهلِك هيبنيها منها (راجع app.core.kernel.auth.step_up)،
    وإلا الـscope_hash هيختلف والاستهلاك هيترفض بـSTEP_UP_INVALID.

    ``totp_offset_steps``: لازم قيمة غير صفرية (مثلاً 1) لو الاختبار محتاج
    يصدر أكتر من step-up token لنفس الحساب خلال نفس نافذة الـ30 ثانية —
    نفس كود TOTP بيتحسب بنفس step_up_token counter، فإعادة استخدامه
    بترفض عمدًا (حماية من إعادة استخدام كود 2FA، راجع
    AuthService._consume_totp_code). الإزاحة لازم تفضل جوه نافذة التفاوت
    المقبولة (±1 خطوة، راجع _matching_totp_step)."""
    import pyotp  # noqa: PLC0415
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    payload: dict = {"current_password": password, "purpose": purpose, "intent": intent}
    if totp_secret:
        totp = pyotp.TOTP(totp_secret)
        at_time = datetime.now(timezone.utc) + timedelta(seconds=totp_offset_steps * totp.interval)
        payload["totp_code"] = totp.at(at_time)
    if recovery_code:
        payload["recovery_code"] = recovery_code
    resp = client.post("/api/v1/auth/step-up", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["step_up_token"]


# Gate 2B3A: سرّ TOTP حقيقي وثابت (مش مجرد two_factor_enabled=True) —
# super_admin@test.local/accountant@test.local مشتركين بين ملفات تستات
# كتير (scope=function لكن الصف نفسه بيتعمله get-or-create مرة واحدة فعليًا
# طول الـsession، راجع setup_db أعلاه)، فالسرّ لازم يبقى ثابت عبر كل
# الاختبارات اللي بتستخدم _issue_step_up مع الحسابين دول.
SUPER_ADMIN_TOTP_SECRET = "JBSWY3DPEHPK3PXP"
ACCOUNTANT_TOTP_SECRET = "KRSXG5CTMVRXEZLU"


def _fresh_super_admin(email_prefix: str = "sa") -> tuple[int, dict[str, str], str]:
    """super_admin جديد ومعزول (uuid عشوائي، سرّ TOTP خاص بيه) — لازم لأي
    اختبار Gate 2B3A محتاج يصدر أكتر من step-up token واحد خلال نفس نافذة
    الـ30 ثانية (شارك حساب super_admin@test.local الثابت هيصطدم بحماية
    إعادة استخدام كود TOTP، راجع AuthService._consume_totp_code — لكل
    حساب counter منفصل، فحساب جديد = نافذة جديدة تمامًا). بيرجع
    (user_id, headers, totp_secret)."""
    import uuid  # noqa: PLC0415
    import pyotp  # noqa: PLC0415

    email = f"{email_prefix}-{uuid.uuid4().hex[:8]}@test.local"
    secret = pyotp.random_base32()
    user_id = _create_test_user(email, "super_admin", two_factor_secret=secret)
    headers = {"Authorization": f"Bearer {_make_token(email)}"}
    return user_id, headers, secret


@pytest.fixture
def super_admin_headers(setup_db) -> dict[str, str]:
    # super_admin لازم 2FA (MANDATORY_2FA_ROLES) — نعتبره مفعّل مسبقاً للاختبار
    _create_test_user("super_admin@test.local", "super_admin", two_factor_secret=SUPER_ADMIN_TOTP_SECRET)
    return {"Authorization": f"Bearer {_make_token('super_admin@test.local')}"}


@pytest.fixture
def manager_headers(setup_db) -> dict[str, str]:
    _create_test_user("manager@test.local", "manager")
    return {"Authorization": f"Bearer {_make_token('manager@test.local')}"}


@pytest.fixture
def accountant_headers(setup_db) -> dict[str, str]:
    # accountant ضمن MANDATORY_2FA_ROLES — لازم two_factor_enabled=True هنا
    # بنفس سبب super_admin_headers فوق، وإلا get_current_active_user يرفض.
    _create_test_user("accountant@test.local", "accountant", two_factor_secret=ACCOUNTANT_TOTP_SECRET)
    return {"Authorization": f"Bearer {_make_token('accountant@test.local')}"}


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
