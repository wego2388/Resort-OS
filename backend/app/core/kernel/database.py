"""
app/core/kernel/database.py
SQLAlchemy engine, session, declarative Base — owned by resort-os.

Call init_db(url) once at app startup, then use get_db() as a FastAPI
dependency. Base is the single declarative base every model in the
project (auth models included) attaches to.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.pool import QueuePool
from typing import Generator, Optional
import os

Base = declarative_base()

_engine = None
_SessionLocal = None


def init_db(database_url: Optional[str] = None) -> None:
    global _engine, _SessionLocal
    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL is not set")
    _engine = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_engine():
    if _engine is None:
        init_db()
    return _engine


def get_db() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        init_db()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
