"""add source tracking to pois and stays

Revision ID: a47e86ebeb34
Revises: ef64db5de951
Create Date: 2026-08-10 10:51:21.647685
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a47e86ebeb34'
down_revision: Union[str, None] = 'ef64db5de951'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pois', sa.Column('source', sa.String(length=50), nullable=True))
    op.add_column('pois', sa.Column('source_id', sa.String(length=255), nullable=True))
    op.add_column('pois', sa.Column('verified_at', sa.Date(), nullable=True))
    op.create_index('ix_pois_source', 'pois', ['source'])
    op.create_index('ix_pois_source_id', 'pois', ['source_id'])

    op.add_column('stays', sa.Column('source', sa.String(length=50), nullable=True))
    op.add_column('stays', sa.Column('source_id', sa.String(length=255), nullable=True))
    op.add_column('stays', sa.Column('verified_at', sa.Date(), nullable=True))
    op.create_index('ix_stays_source', 'stays', ['source'])
    op.create_index('ix_stays_source_id', 'stays', ['source_id'])


def downgrade() -> None:
    op.drop_index('ix_pois_source', table_name='pois')
    op.drop_index('ix_pois_source_id', table_name='pois')
    op.drop_column('pois', 'source')
    op.drop_column('pois', 'source_id')
    op.drop_column('pois', 'verified_at')

    op.drop_index('ix_stays_source', table_name='stays')
    op.drop_index('ix_stays_source_id', table_name='stays')
    op.drop_column('stays', 'source')
    op.drop_column('stays', 'source_id')
    op.drop_column('stays', 'verified_at')
