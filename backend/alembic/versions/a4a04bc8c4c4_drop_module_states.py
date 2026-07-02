"""drop_module_states

Revision ID: a4a04bc8c4c4
Revises: d4feecc4b488
Create Date: 2026-07-02

Removes the module enable/disable toggle system entirely — every module is
now permanently active (same as core/finance/inventory/hr always were).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a4a04bc8c4c4'
down_revision: Union[str, None] = 'd4feecc4b488'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('module_states')


def downgrade() -> None:
    op.create_table(
        'module_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('module_key', sa.String(length=50), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('changed_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id']),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('module_key', 'branch_id', name='uq_module_branch'),
    )
    op.create_index(op.f('ix_module_states_branch_id'), 'module_states', ['branch_id'], unique=False)
