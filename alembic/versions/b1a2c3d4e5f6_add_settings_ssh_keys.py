"""add settings ssh_keys tables and server ssh_key_id

Revision ID: b1a2c3d4e5f6
Revises: f0dde358a7f3
Create Date: 2026-04-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f0dde358a7f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add settings and ssh_keys tables, modify servers."""
    # Settings key-value table
    op.create_table('settings',
        sa.Column('key', sa.String(length=128), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('is_secret', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('requires_restart', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )

    # SSH keys table
    op.create_table('ssh_keys',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('private_key', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Add ssh_key_id FK to servers, drop ssh_key_path and ssh_password
    op.add_column('servers', sa.Column('ssh_key_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_servers_ssh_key_id', 'servers', 'ssh_keys', ['ssh_key_id'], ['id'])
    op.drop_column('servers', 'ssh_key_path')
    op.drop_column('servers', 'ssh_password')


def downgrade() -> None:
    """Revert: drop settings, ssh_keys; restore ssh_key_path/ssh_password on servers."""
    op.add_column('servers', sa.Column('ssh_password', sa.String(length=256), nullable=True))
    op.add_column('servers', sa.Column('ssh_key_path', sa.String(length=512), nullable=True))
    op.drop_constraint('fk_servers_ssh_key_id', 'servers', type_='foreignkey')
    op.drop_column('servers', 'ssh_key_id')
    op.drop_table('ssh_keys')
    op.drop_table('settings')
