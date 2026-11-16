"""runs.security_level: a routine's run keeps the level it started at

Revision ID: c3d81f2a6b57
Revises: 8cf59be5197c
Create Date: 2026-11-16 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d81f2a6b57"
down_revision: str | Sequence[str] | None = "8cf59be5197c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive. Runs a routine already started keep its level (the run reads the strictest of it
    and its bot's), so removing the routine later can't loosen them."""
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("security_level", sa.String(length=30), nullable=True))
    op.execute(
        "UPDATE runs SET security_level = (SELECT routines.security_level FROM routine_runs"
        " JOIN routines ON routines.id = routine_runs.routine_id WHERE routine_runs.run_id = runs.id)"
        " WHERE EXISTS (SELECT 1 FROM routine_runs WHERE routine_runs.run_id = runs.id)"
    )


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("security_level")
