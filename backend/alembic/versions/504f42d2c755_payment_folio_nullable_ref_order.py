"""payment: folio_id nullable + ref_order_id

Direct POS sales (dining/beach/cafe) don't go through a Folio — they pay
directly via cash/card at the counter. Making folio_id nullable lets us
record a Payment with a shift_id so cashier-shift reports see real totals.
ref_order_id links the payment back to the originating DiningOrder.

Revision ID: 504f42d2c755
Revises: 8914aff96da6
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = '504f42d2c755'
down_revision = '8914aff96da6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. اجعل folio_id nullable (direct POS sales بدون folio)
    op.alter_column('payments', 'folio_id',
                    existing_type=sa.Integer(),
                    nullable=True)

    # 2. أضف ref_order_id لو مش موجود
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('payments')]
    if 'ref_order_id' not in cols:
        op.add_column('payments',
                      sa.Column('ref_order_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    # حذف السجلات اللي folio_id=NULL قبل الـ downgrade
    op.execute("DELETE FROM payments WHERE folio_id IS NULL")
    op.alter_column('payments', 'folio_id',
                    existing_type=sa.Integer(),
                    nullable=False)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('payments')]
    if 'ref_order_id' in cols:
        op.drop_column('payments', 'ref_order_id')
