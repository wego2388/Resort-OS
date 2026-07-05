"""pms: add rate_plan_id to booking_rooms

Revision ID: b2d7f931a4e1
Revises: a1c9e2f4b8d3
Create Date: 2026-07-05 19:00:00.000000

باج "الموديل موجود، الـ API صفر" (RatePlan) اتصلح جزئيًا اليوم بربط
GET/POST /pms/rate-plans بالفعل — بس create_booking نفسها كانت لسه
بتسعّر كل غرفة بـ room_type.base_rate الخام دايمًا، من غير ما تدّي أي
فرصة لخطة أسعار موسمية (RatePlan) تتطبّق فعليًا. العمود ده بيسجّل خطة
الأسعار اللي اتطبّقت فعليًا (لو حصل) على كل غرفة في الحجز، لأغراض
العرض/المراجعة — nullable لأن أغلب الحجوزات (السعر الأساسي بدون خطة
موسمية) هتفضل من غيره.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2d7f931a4e1'
down_revision: Union[str, None] = 'b4d8f1a3c6e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'booking_rooms',
        sa.Column('rate_plan_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_booking_rooms_rate_plan_id', 'booking_rooms', 'rate_plans',
        ['rate_plan_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(
        op.f('ix_booking_rooms_rate_plan_id'), 'booking_rooms', ['rate_plan_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_booking_rooms_rate_plan_id'), table_name='booking_rooms')
    op.drop_constraint('fk_booking_rooms_rate_plan_id', 'booking_rooms', type_='foreignkey')
    op.drop_column('booking_rooms', 'rate_plan_id')
