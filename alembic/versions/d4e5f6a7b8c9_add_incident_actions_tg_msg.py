"""add actions_json and tg_message_id to incidents

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('incidents', sa.Column('actions_json', sa.JSON(), nullable=True))
    op.add_column('incidents', sa.Column('tg_message_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('incidents', 'tg_message_id')
    op.drop_column('incidents', 'actions_json')
