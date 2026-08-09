"""room garden_view type and occupancy per room type

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-09

Mohamed approved:
- Studio   → max_occupancy = 2
- Chalet   → max_occupancy = 4
- 7 units currently stored as view_type='none' become 'garden_view'
- CheckConstraint extended to allow 'garden_view'
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None

# الغرف اللي كانت 'none' وبقت 'garden_view'
GARDEN_VIEW_ROOMS = ("101A", "102A", "102S", "103A", "124S", "111A", "111S")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. حذف الـ constraint القديم
    op.drop_constraint("ck_rooms_view_type_valid", "rooms", type_="check")

    # 2. تحديث view_type من 'none' إلى 'garden_view' للوحدات المعتمدة
    bind.execute(
        sa.text(
            "UPDATE rooms SET view_type = 'garden_view' "
            "WHERE name IN :names AND view_type = 'none'"
        ),
        {"names": GARDEN_VIEW_ROOMS},
    )

    # 3. إضافة الـ constraint الجديد يشمل 'garden_view'
    op.create_check_constraint(
        "ck_rooms_view_type_valid",
        "rooms",
        "view_type IN ('none', 'garden_view', 'side_sea', 'sea')",
    )

    # 4. تحديث max_occupancy للنوعين
    bind.execute(
        sa.text(
            "UPDATE room_types SET max_occupancy = 2 WHERE name = 'Studio'"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE room_types SET max_occupancy = 4 WHERE name = 'Chalet'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()

    # تفريغ max_occupancy
    bind.execute(
        sa.text(
            "UPDATE room_types SET max_occupancy = NULL "
            "WHERE name IN ('Studio', 'Chalet')"
        )
    )

    # إعادة garden_view إلى none
    bind.execute(
        sa.text(
            "UPDATE rooms SET view_type = 'none' WHERE view_type = 'garden_view'"
        )
    )

    # إعادة الـ constraint القديم
    op.drop_constraint("ck_rooms_view_type_valid", "rooms", type_="check")
    op.create_check_constraint(
        "ck_rooms_view_type_valid",
        "rooms",
        "view_type IN ('none', 'side_sea', 'sea')",
    )
