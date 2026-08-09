"""timeshare room_type 2R/4R/6R → Studio/Chalet

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-09

Mohamed approved:
- Studio  = 2 persons  (was 2R)
- Chalet  = 4 persons  (was 4R)
- 6-person stay = Chalet + Studio booked together (two separate units)
  → 6R contracts are migrated to Chalet (the primary unit in the combo)

timeshare_contracts.room_type  and timeshare_units.unit_type both updated.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

_MAPPING = {"2R": "Studio", "4R": "Chalet", "6R": "Chalet"}


def upgrade() -> None:
    bind = op.get_bind()
    for old, new in _MAPPING.items():
        bind.execute(
            sa.text(
                "UPDATE timeshare_contracts SET room_type = :new WHERE room_type = :old"
            ),
            {"new": new, "old": old},
        )
        bind.execute(
            sa.text(
                "UPDATE timeshare_units SET unit_type = :new WHERE unit_type = :old"
            ),
            {"new": new, "old": old},
        )


def downgrade() -> None:
    bind = op.get_bind()
    # لا يمكن التراجع بدقة: 4R و6R كلاهما أصبح Chalet
    # الـ downgrade يعيد Chalet → 4R فقط (6R ضاع معلوماتيًا)
    bind.execute(
        sa.text(
            "UPDATE timeshare_contracts SET room_type = '4R' WHERE room_type = 'Chalet'"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE timeshare_contracts SET room_type = '2R' WHERE room_type = 'Studio'"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE timeshare_units SET unit_type = '4R' WHERE unit_type = 'Chalet'"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE timeshare_units SET unit_type = '2R' WHERE unit_type = 'Studio'"
        )
    )
