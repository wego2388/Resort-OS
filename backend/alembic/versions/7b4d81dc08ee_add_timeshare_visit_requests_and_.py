"""add timeshare visit requests and support tickets

Revision ID: 7b4d81dc08ee
Revises: 7e5e126360d5
Create Date: 2026-08-03 12:33:21.699728

⚠️ ملاحظة: autogenerate رجّع كمان تغييرات غير مرتبطة خالص (chat_public_facts/
chat_messages/chat_conversations، وindex في timeshare_maintenance_dues،
وtype على user_branch_memberships) — drift موجود في قاعدة البيانات المحلية
من شغل تاني غير مكتمل (migration)، مش من التعديل ده. اتشالت يدويًا من هنا
عمدًا — الـmigration دي بتضيف الـ3 جداول الجداد بتوع بوابة العميل/طلبات
الزيارة/تذاكر الدعم بس، زي ما طلب Mohamed بالظبط.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7b4d81dc08ee'
down_revision: Union[str, None] = '7e5e126360d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('timeshare_support_tickets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('contract_id', sa.Integer(), nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('assigned_to', sa.Integer(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contract_id'], ['timeshare_contracts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_timeshare_support_tickets_contract_id'), 'timeshare_support_tickets', ['contract_id'], unique=False)
    op.create_index(op.f('ix_timeshare_support_tickets_status'), 'timeshare_support_tickets', ['status'], unique=False)
    op.create_table('timeshare_support_ticket_replies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ticket_id', sa.Integer(), nullable=False),
    sa.Column('author_type', sa.String(length=10), nullable=False),
    sa.Column('author_user_id', sa.Integer(), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['ticket_id'], ['timeshare_support_tickets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_timeshare_support_ticket_replies_ticket_id'), 'timeshare_support_ticket_replies', ['ticket_id'], unique=False)
    op.create_table('timeshare_visit_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('contract_id', sa.Integer(), nullable=False),
    sa.Column('preferred_start', sa.Date(), nullable=False),
    sa.Column('preferred_end', sa.Date(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('reviewed_by', sa.Integer(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(), nullable=True),
    sa.Column('rejection_reason', sa.String(length=300), nullable=True),
    sa.Column('visit_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contract_id'], ['timeshare_contracts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['visit_id'], ['timeshare_visits.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_timeshare_visit_requests_contract_id'), 'timeshare_visit_requests', ['contract_id'], unique=False)
    op.create_index(op.f('ix_timeshare_visit_requests_status'), 'timeshare_visit_requests', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_timeshare_visit_requests_status'), table_name='timeshare_visit_requests')
    op.drop_index(op.f('ix_timeshare_visit_requests_contract_id'), table_name='timeshare_visit_requests')
    op.drop_table('timeshare_visit_requests')
    op.drop_index(op.f('ix_timeshare_support_ticket_replies_ticket_id'), table_name='timeshare_support_ticket_replies')
    op.drop_table('timeshare_support_ticket_replies')
    op.drop_index(op.f('ix_timeshare_support_tickets_status'), table_name='timeshare_support_tickets')
    op.drop_index(op.f('ix_timeshare_support_tickets_contract_id'), table_name='timeshare_support_tickets')
    op.drop_table('timeshare_support_tickets')
