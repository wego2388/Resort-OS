"""
app/modules/owner/db_sessions.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — restricted database sessions.
Decision 0004 §Isolation model item 5; security review 2026-08-11.

الفكرة: قيد صلاحيات حقيقي على مستوى Postgres role نفسه — مش بس مراجعة
كود. لو bug مستقبلي في أي service function حاول (غلط) يكتب على جدول
تشغيلي من مسار owner، القفل الحقيقي بيرفضه على مستوى الداتابيز قبل ما
يوصل، مش معتمد بس على إن كل الكود الحالي صحيح اليوم.

  • OwnerReadSession           — SELECT بس، على كل الجداول. تُستخدم في كل
    endpoint تجميع/تقرير (GET /owner/now، /performance، ...).
  • OwnerMetadataWriteSession  — INSERT/UPDATE/DELETE بس على
    owner_watchlist وowner_allocation_rules، مفيش وصول لأي جدول تشغيلي
    تاني. تُستخدم في كتابات watchlist ومسودات allocation rule فقط.

التزويد الفعلي (CREATE ROLE + GRANT) في scripts/provision_owner_db_roles.sql
— منفصل عمدًا عن alembic migrations (صلاحيات DB roles مسؤولية DBA/
deployment لكل بيئة، مش schema migration عادي بيتكرر على كل بيئة زي ما
هو). لو OWNER_READ_DATABASE_URL/OWNER_METADATA_WRITE_DATABASE_URL مش
متضبطين في env (بيئة تطوير محلية عادةً، أو قبل تشغيل سكريبت التزويد)،
السيشنين بيرجعوا لنفس الـengine العادي (app.core.database.get_db) بدل
ما يفشلوا — القيد الحقيقي بيتفعّل بس لما DSN فعلي بصلاحية محدودة يتظبط،
وده بالظبط اللي tests/test_owner_db_session_privileges.py (Postgres-only)
بيثبته حي.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.database import get_db as get_default_db

_read_engine = None
_read_session_local = None
_metadata_write_engine = None
_metadata_write_session_local = None


def _read_sessionmaker():
    global _read_engine, _read_session_local
    url = get_settings().OWNER_READ_DATABASE_URL
    if not url:
        return None
    if _read_session_local is None:
        _read_engine = create_engine(url, pool_pre_ping=True)
        _read_session_local = sessionmaker(autocommit=False, autoflush=False, bind=_read_engine)
    return _read_session_local


def _metadata_write_sessionmaker():
    global _metadata_write_engine, _metadata_write_session_local
    url = get_settings().OWNER_METADATA_WRITE_DATABASE_URL
    if not url:
        return None
    if _metadata_write_session_local is None:
        _metadata_write_engine = create_engine(url, pool_pre_ping=True)
        _metadata_write_session_local = sessionmaker(autocommit=False, autoflush=False, bind=_metadata_write_engine)
    return _metadata_write_session_local


def get_owner_read_db() -> Generator[Session, None, None]:
    """كل تقارير تجميع owner (GET) — SELECT بس على مستوى الـPostgres role
    نفسه لو OWNER_READ_DATABASE_URL متظبط، وإلا fallback للسيشن العادي."""
    factory = _read_sessionmaker()
    if factory is None:
        yield from get_default_db()
        return
    db = factory()
    try:
        yield db
    finally:
        db.close()


def get_owner_metadata_write_db() -> Generator[Session, None, None]:
    """كتابات owner_watchlist/owner_allocation_rules (drafts) بس."""
    factory = _metadata_write_sessionmaker()
    if factory is None:
        yield from get_default_db()
        return
    db = factory()
    try:
        yield db
    finally:
        db.close()
