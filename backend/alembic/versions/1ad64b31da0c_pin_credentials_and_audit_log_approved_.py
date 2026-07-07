"""pin_credentials and audit_log approved_by

Revision ID: 1ad64b31da0c
Revises: c4a7f0e2b619
Create Date: 2026-07-07 21:41:57.008109

ملحوظة: autogenerate رجّع كمية كبيرة من فروقات indexes/foreign-keys غير
متعلقة بالتعديل ده خالص (على attendance_records، beach_*، bookings،
cafe_item_recipe_lines، conditional_discounts، folio_charges، folios،
housekeeping_tasks، menu_item_recipe_lines، notifications، orders، rooms،
settings) — دي فروقات تسمية pre-existing بين naming convention القديم
والحالي، مش تغيير حقيقي طلبته الميجريشن دي. اتشالت عمدًا من هنا (out of
scope — لمسها كان هيوسّع نطاق ميجريشن PIN لجداول مالية/تشغيلية تانية بدون
أي داعي حقيقي). لو حد احتاج ينضّف الفروقات دي فعليًا، محتاجة migration
منفصلة مركّزة على ده بس، بعد مراجعة كل واحدة لوحدها.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1ad64b31da0c'
down_revision: Union[str, None] = 'c4a7f0e2b619'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pin_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('pin_hash', sa.String(length=255), nullable=False),
        sa.Column('failed_attempts', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pin_credentials_user_id'), 'pin_credentials', ['user_id'], unique=True)

    op.add_column('audit_logs', sa.Column('approved_by', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_audit_logs_approved_by'), 'audit_logs', ['approved_by'], unique=False)
    op.create_foreign_key(
        'audit_logs_approved_by_fkey', 'audit_logs', 'users', ['approved_by'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('audit_logs_approved_by_fkey', 'audit_logs', type_='foreignkey')
    op.drop_index(op.f('ix_audit_logs_approved_by'), table_name='audit_logs')
    op.drop_column('audit_logs', 'approved_by')

    op.drop_index(op.f('ix_pin_credentials_user_id'), table_name='pin_credentials')
    op.drop_table('pin_credentials')
