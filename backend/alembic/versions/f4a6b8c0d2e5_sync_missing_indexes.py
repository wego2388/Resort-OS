"""sync_missing_indexes

Revision ID: f4a6b8c0d2e5
Revises: e3f5a7b9c2d4
Create Date: 2026-07-24 21:22:00.000000

يضيف الـ indexes الموجودة في DB لكن غير معرّفة في models SQLAlchemy
(Alembic autogenerate بيعتبرها drift).
هذه indexes مهمة للـ performance وتبقى في DB.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = 'f4a6b8c0d2e5'
down_revision: Union[str, None] = 'e3f5a7b9c2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # الـ indexes دي موجودة في DB — لا نحذفها ولا نعيد إنشاءها
    # هذا الـ migration فقط لمزامنة alembic_version مع الـ drift المتبقي
    # (الـ indexes نفسها موجودة بالفعل من migrations سابقة)
    pass


def downgrade() -> None:
    pass
