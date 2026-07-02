"""
app/core/encryption.py
Application-level field encryption for sensitive columns (national_id, passport
number, etc.) per 08-SECURITY.md — wego_core has no EncryptedString column type
by design, so each consuming project implements its own with Fernet.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import String, TypeDecorator

from app.core.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not settings.FIELD_ENCRYPTION_KEY:
            raise RuntimeError(
                "FIELD_ENCRYPTION_KEY غير مُعرَّف في .env — مطلوب لتشفير الحقول الحساسة"
            )
        _fernet = Fernet(settings.FIELD_ENCRYPTION_KEY.encode())
    return _fernet


class EncryptedString(TypeDecorator):
    """
    Transparent Fernet encryption for a String column — encrypt on write,
    decrypt on read. Use for national_id / passport_number / similar PII.

        national_id: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None or value == "":
            return value
        return _get_fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None or value == "":
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            # قيمة قديمة كُتبت قبل تفعيل التشفير — تُرجع كما هي بدلاً من كسر الـ request
            return value
