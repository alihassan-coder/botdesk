"""A message sent with "send now" while a bot works (ADR 0022): its queued run is marked, so the
working run of the same bot can take the message at its next step.

Revision ID: c6d2e8a4f1b7
Revises: b8e4f2a6c157
Create Date: 2026-11-27 20:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6d2e8a4f1b7"
down_revision: str | Sequence[str] | None = "b8e4f2a6c157"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Every existing run was sent the old way (it waits its turn)."""
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deliver_now", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("deliver_now")
