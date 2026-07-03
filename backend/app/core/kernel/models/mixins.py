"""
app/core/kernel/models/mixins.py
SQLAlchemy mixins shared across resort-os models.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, TIMESTAMP
from sqlalchemy.sql import func


class TimestampMixin:
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)


class SoftDeleteMixin:
    deleted_at = Column(TIMESTAMP, nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = datetime.now(timezone.utc)
