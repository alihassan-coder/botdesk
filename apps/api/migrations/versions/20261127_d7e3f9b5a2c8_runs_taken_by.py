"""A message taken by a working run (ADR 0022) remembers which run took it, so that run can read it
again after a restart, or give it back if the step that took it failed.

Revision ID: d7e3f9b5a2c8
Revises: c6d2e8a4f1b7
Create Date: 2026-11-27 21:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7e3f9b5a2c8"
down_revision: str | Sequence[str] | None = "c6d2e8a4f1b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK = "fk_runs_taken_by_run_id_runs"


def upgrade() -> None:
    """No run has taken a message yet in the old way's sense: every row starts unlinked."""
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("taken_by_run_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(FK, "runs", ["taken_by_run_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_constraint(FK, type_="foreignkey")
        batch_op.drop_column("taken_by_run_id")
