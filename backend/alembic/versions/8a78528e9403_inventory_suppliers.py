"""inventory_suppliers

Revision ID: 8a78528e9403
Revises: 23e4eca09fe0
Create Date: 2026-07-13 00:00:00.000000

Batch 1 من طلب Mohamed (مقارنة Click القديم + elkheima-beach-resort مع
resort-os): PurchaseOrder.supplier_name/supplier_phone كانوا نص حر بدون
كيان Supplier حقيقي، رغم إن سير عمل الاستلام الحقيقي (crud.receive_
purchase_order) بيأثر في المخزون فعليًا بالفعل (SELECT FOR UPDATE NOWAIT +
متوسط تكلفة متحرك — الجزء ده متلمسش هنا خالص). الشكل مبني على `Supplier`
في نظام elkheima-beach-resort القديم + حقول موسّعة (contact_person/address/
tax_number/payment_terms_days/credit_limit).

الخطوات:
1. إنشاء جدول suppliers.
2. إضافة purchase_orders.supplier_id (FK، nullable) + تخفيف supplier_name
   لـ nullable (كان NOT NULL — لازم يبقى nullable عشان الأوامر الجديدة
   اللي بتحدد supplier_id بس تقدر تسيبه فاضي وقت الإنشاء، مع إن crud.
   create_purchase_order بيعبّيه تلقائيًا من المورد كلقطة عادةً).
3. Backfill أفضل-محاولة (best-effort): لكل (branch_id, supplier_name) مميز
   وموجود فعليًا على purchase_orders — دوّر على Supplier بنفس الاسم
   بالظبط في نفس الفرع؛ لو مالقيتش، اعمل واحد جديد (حتى لو الاسم كان
   "TBD (من طلب شراء #N)" — قيمة placeholder قديمة من باج services.
   convert_to_purchase_order قبل إصلاحه في نفس الدفعة دي، بيتحفظله سجل
   Supplier حقيقي بدل ما يضيع، وقابل للتصحيح لاحقًا من شاشة الموردين).
   بعدين حدّث purchase_orders.supplier_id لكل الصفوف المطابقة. Idempotent:
   UPDATE بس على صفوف supplier_id IS NULL، ومطابقة الاسم قبل الإنشاء —
   إعادة تشغيل الـ migration (upgrade→downgrade→upgrade) ميضاعفش الموردين.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '8a78528e9403'
down_revision: Union[str, None] = '23e4eca09fe0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'suppliers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('name_ar', sa.String(200), nullable=True),
        sa.Column('contact_person', sa.String(150), nullable=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('email', sa.String(150), nullable=True),
        sa.Column('address', sa.String(300), nullable=True),
        sa.Column('tax_number', sa.String(50), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('payment_terms_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('credit_limit', sa.Numeric(12, 2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_suppliers_branch_id', 'suppliers', ['branch_id'])

    op.add_column(
        'purchase_orders',
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_purchase_orders_supplier_id', 'purchase_orders', ['supplier_id'])
    op.alter_column('purchase_orders', 'supplier_name', existing_type=sa.String(200), nullable=True)

    bind = op.get_bind()

    # ── Backfill: أفضل-محاولة (best-effort) لكل (branch_id, supplier_name) ──
    distinct_names = bind.execute(sa.text("""
        SELECT DISTINCT branch_id, supplier_name
        FROM purchase_orders
        WHERE supplier_id IS NULL
          AND supplier_name IS NOT NULL
          AND TRIM(supplier_name) <> ''
    """)).fetchall()

    for branch_id, supplier_name in distinct_names:
        existing = bind.execute(sa.text("""
            SELECT id FROM suppliers WHERE branch_id = :branch_id AND name = :name
        """), {"branch_id": branch_id, "name": supplier_name}).fetchone()

        if existing:
            supplier_id = existing[0]
        else:
            # نجيب أول رقم تليفون مسجّل لنفس الاسم/الفرع (لو موجود) كلقطة
            # أولى للمورد الجديد — أفضل من فاضي، مش مصدر حقيقة نهائي.
            phone_row = bind.execute(sa.text("""
                SELECT supplier_phone FROM purchase_orders
                WHERE branch_id = :branch_id AND supplier_name = :name
                  AND supplier_phone IS NOT NULL AND TRIM(supplier_phone) <> ''
                LIMIT 1
            """), {"branch_id": branch_id, "name": supplier_name}).fetchone()
            phone = phone_row[0] if phone_row else None

            result = bind.execute(sa.text("""
                INSERT INTO suppliers (branch_id, name, phone, is_active, created_at, updated_at)
                VALUES (:branch_id, :name, :phone, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
            """), {"branch_id": branch_id, "name": supplier_name, "phone": phone})
            supplier_id = result.fetchone()[0]

        bind.execute(sa.text("""
            UPDATE purchase_orders SET supplier_id = :supplier_id
            WHERE branch_id = :branch_id AND supplier_name = :name AND supplier_id IS NULL
        """), {"supplier_id": supplier_id, "branch_id": branch_id, "name": supplier_name})


def downgrade() -> None:
    op.alter_column('purchase_orders', 'supplier_name', existing_type=sa.String(200), nullable=False)
    op.drop_index('ix_purchase_orders_supplier_id', table_name='purchase_orders')
    op.drop_column('purchase_orders', 'supplier_id')
    op.drop_index('ix_suppliers_branch_id', table_name='suppliers')
    op.drop_table('suppliers')
