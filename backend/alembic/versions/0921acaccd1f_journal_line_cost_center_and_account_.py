"""journal_line_cost_center_and_account_hierarchy

Revision ID: 0921acaccd1f
Revises: 561c30b7cc11
Create Date: 2026-07-14 00:00:00.000000

Batch 3 من طلب Mohamed (مقارنة Click القديم + elkheima-beach-resort):
1. journal_lines.cost_center_id (FK nullable لـ cost_centers) — يُوسَم وقت
   الترحيل نفسه في dining/beach/pms/timeshare/inventory.services (راجع
   finance.services.post_simple_revenue_journal's cost_center_code)، مش
   يتستنتج بعدين من جداول عمليات منفصلة زي finance.services.
   get_cost_center_report كان بيعمل قبل كده.
2. تفعيل Account.parent_id (كان موجود في الـ schema من زمان، بدون أي
   استخدام) — 4 حسابات أب (رؤوس مجموعات، مستوى واحد بس): الأصول (1000)/
   الخصوم (2000)/الإيرادات (4000)/المصروفات (5000). كل حساب من الـ 22
   الموجودين فعليًا (على أي فرع، مش بس الفرع المزروع بـ seed.py) بيتحدد
   له أب حسب account_type — data backfill idempotent (بيتخطى أي حساب
   عنده parent_id بالفعل).

Idempotent بالكامل: أعمدة/جداول جديدة بس، وUPDATE مشروط بـ parent_id IS
NULL — إعادة تشغيل الـ migration (upgrade→downgrade→upgrade) آمنة.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0921acaccd1f'
down_revision: Union[str, None] = '561c30b7cc11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PARENT_HEADERS = [
    ("1000", "الأصول", "asset"),
    ("2000", "الخصوم", "liability"),
    ("4000", "الإيرادات", "revenue"),
    ("5000", "المصروفات", "expense"),
]


def upgrade() -> None:
    op.add_column(
        'journal_lines',
        sa.Column('cost_center_id', sa.Integer(), sa.ForeignKey('cost_centers.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_journal_lines_cost_center_id', 'journal_lines', ['cost_center_id'])

    bind = op.get_bind()

    # لكل فرع عنده حسابات فعليًا — ازرع رؤوس المجموعات الأربعة لو مش
    # موجودة، وبعدين احدث parent_id لأي حساب من غير أب (idempotent).
    branch_ids = [row[0] for row in bind.execute(sa.text(
        "SELECT DISTINCT branch_id FROM accounts",
    )).fetchall()]

    for branch_id in branch_ids:
        header_id_by_type: dict[str, int] = {}
        for code, name, account_type in _PARENT_HEADERS:
            existing = bind.execute(sa.text("""
                SELECT id FROM accounts WHERE branch_id = :branch_id AND code = :code
            """), {"branch_id": branch_id, "code": code}).fetchone()
            if existing:
                header_id_by_type[account_type] = existing[0]
            else:
                result = bind.execute(sa.text("""
                    INSERT INTO accounts (branch_id, code, name, account_type, parent_id, is_active, created_at, updated_at)
                    VALUES (:branch_id, :code, :name, :account_type, NULL, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                """), {"branch_id": branch_id, "code": code, "name": name, "account_type": account_type})
                header_id_by_type[account_type] = result.fetchone()[0]

        for account_type, header_id in header_id_by_type.items():
            bind.execute(sa.text("""
                UPDATE accounts SET parent_id = :header_id
                WHERE branch_id = :branch_id AND account_type = :account_type
                  AND parent_id IS NULL AND id != :header_id
            """), {"header_id": header_id, "branch_id": branch_id, "account_type": account_type})


def downgrade() -> None:
    op.drop_index('ix_journal_lines_cost_center_id', table_name='journal_lines')
    op.drop_column('journal_lines', 'cost_center_id')
    # ملاحظة: downgrade عمدًا مش بيمسح parent_id ولا حسابات الرؤوس (1000/
    # 2000/4000/5000) — مسحهم ممكن يكسر FK لو حسابات تانية اتضافت تحتهم
    # بعد الترقية، ومفيش خطر محاسبي من إبقائهم (أعمدة/صفوف زيادة بس).
