"""fix cascade foreign keys for server deletion

Revision ID: c3d4e5f6a7b8
Revises: b1a2c3d4e5f6
Create Date: 2026-04-03 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b1a2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix FK cascades: check_runs.server_id CASCADE, incidents.check_run_id SET NULL."""
    # check_runs.server_id → ON DELETE CASCADE
    op.drop_constraint('check_runs_ibfk_1', 'check_runs', type_='foreignkey')
    op.create_foreign_key(
        'check_runs_ibfk_1', 'check_runs', 'servers',
        ['server_id'], ['id'], ondelete='CASCADE',
    )

    # incidents.check_run_id → ON DELETE SET NULL
    op.drop_constraint('incidents_ibfk_1', 'incidents', type_='foreignkey')
    op.create_foreign_key(
        'incidents_ibfk_1', 'incidents', 'check_runs',
        ['check_run_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    """Revert FK cascades."""
    op.drop_constraint('incidents_ibfk_1', 'incidents', type_='foreignkey')
    op.create_foreign_key(
        'incidents_ibfk_1', 'incidents', 'check_runs',
        ['check_run_id'], ['id'],
    )

    op.drop_constraint('check_runs_ibfk_1', 'check_runs', type_='foreignkey')
    op.create_foreign_key(
        'check_runs_ibfk_1', 'check_runs', 'servers',
        ['server_id'], ['id'],
    )
