"""
app/core/kernel/auth/repository.py
Generic repository base + UserRepository.
"""

from datetime import datetime, timezone
from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy import or_
from sqlalchemy.orm import Session

T = TypeVar("T")


class BaseRepository(Generic[T]):
    def __init__(self, model: Type[T], db: Session):
        self.model = model
        self.db = db

    # ── Single record ─────────────────────────────────────────────────────

    def get(self, id: int) -> Optional[T]:
        q = self.db.query(self.model).filter(self.model.id == id)
        if hasattr(self.model, "deleted_at"):
            q = q.filter(self.model.deleted_at.is_(None))
        return q.first()

    def get_or_404(self, id: int, label: str = "Record") -> T:
        obj = self.get(id)
        if not obj:
            from fastapi import HTTPException
            raise HTTPException(404, f"{label} not found (id: {id})")
        return obj

    def get_by_field(self, field: str, value) -> Optional[T]:
        if not hasattr(self.model, field):
            return None
        q = self.db.query(self.model).filter(getattr(self.model, field) == value)
        if hasattr(self.model, "deleted_at"):
            q = q.filter(self.model.deleted_at.is_(None))
        return q.first()

    def exists(self, **filters) -> bool:
        q = self.db.query(self.model.id)
        if hasattr(self.model, "deleted_at"):
            q = q.filter(self.model.deleted_at.is_(None))
        for k, v in filters.items():
            if hasattr(self.model, k):
                q = q.filter(getattr(self.model, k) == v)
        return q.first() is not None

    # ── List / search ─────────────────────────────────────────────────────

    def list(self, skip: int = 0, limit: int = 20, **filters) -> List[T]:
        q = self.db.query(self.model)
        if hasattr(self.model, "deleted_at"):
            q = q.filter(self.model.deleted_at.is_(None))
        for k, v in filters.items():
            if v is not None and hasattr(self.model, k):
                q = q.filter(getattr(self.model, k) == v)
        return q.offset(skip).limit(limit).all()

    def count(self, **filters) -> int:
        q = self.db.query(self.model)
        if hasattr(self.model, "deleted_at"):
            q = q.filter(self.model.deleted_at.is_(None))
        for k, v in filters.items():
            if v is not None and hasattr(self.model, k):
                q = q.filter(getattr(self.model, k) == v)
        return q.count()

    def search(self, query: str, fields: List[str], skip: int = 0, limit: int = 20) -> List[T]:
        if not query or not fields:
            return self.list(skip=skip, limit=limit)
        conditions = []
        for field in fields:
            if hasattr(self.model, field):
                conditions.append(getattr(self.model, field).ilike(f"%{query}%"))
        if not conditions:
            return []
        q = self.db.query(self.model).filter(or_(*conditions))
        if hasattr(self.model, "deleted_at"):
            q = q.filter(self.model.deleted_at.is_(None))
        return q.offset(skip).limit(limit).all()

    # ── Write ─────────────────────────────────────────────────────────────

    def create(self, data: dict) -> T:
        obj = self.model(**data)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def bulk_create(self, data_list: List[dict]) -> List[T]:
        objects = [self.model(**d) for d in data_list]
        self.db.add_all(objects)
        self.db.commit()
        for obj in objects:
            self.db.refresh(obj)
        return objects

    def update(self, id: int, data: dict) -> Optional[T]:
        obj = self.get(id)
        if not obj:
            return None
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def get_or_create(self, defaults: dict, **lookup) -> tuple[T, bool]:
        obj = self.get_by_field(*list(lookup.items())[0]) if len(lookup) == 1 else None
        if obj is None:
            q = self.db.query(self.model)
            for k, v in lookup.items():
                if hasattr(self.model, k):
                    q = q.filter(getattr(self.model, k) == v)
            obj = q.first()
        if obj:
            return obj, False
        obj = self.create({**lookup, **defaults})
        return obj, True

    # ── Delete ────────────────────────────────────────────────────────────

    def delete(self, id: int) -> bool:
        obj = self.get(id)
        if not obj:
            return False
        self.db.delete(obj)
        self.db.commit()
        return True

    def soft_delete(self, id: int) -> bool:
        obj = self.get(id)
        if not obj:
            return False
        if not hasattr(obj, "deleted_at"):
            return self.delete(id)
        obj.deleted_at = datetime.now(timezone.utc)
        self.db.commit()
        return True

    def restore(self, id: int) -> bool:
        q = self.db.query(self.model).filter(self.model.id == id)
        if not hasattr(self.model, "deleted_at"):
            return False
        obj = q.first()
        if not obj or obj.deleted_at is None:
            return False
        obj.deleted_at = None
        self.db.commit()
        return True


class UserRepository(BaseRepository):
    """Works with any User model — inject the model class at construction."""

    def __init__(self, model, db: Session):
        super().__init__(model, db)

    def get_by_email(self, email: str):
        q = self.db.query(self.model).filter(self.model.email == email)
        if hasattr(self.model, "deleted_at"):
            q = q.filter(self.model.deleted_at.is_(None))
        return q.first()

    def get_active_by_email(self, email: str):
        return self.db.query(self.model).filter(
            self.model.email == email,
            self.model.is_active == True,  # noqa: E712
        ).first()

    def list_by_role(self, role: str, skip: int = 0, limit: int = 100):
        return self.db.query(self.model).filter(
            self.model.role == role
        ).offset(skip).limit(limit).all()
