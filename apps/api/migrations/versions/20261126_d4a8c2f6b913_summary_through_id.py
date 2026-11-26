"""A chat summary also records the id of the newest message it covers, so messages written at
the same moment are told apart (ADR 0019).

Revision ID: d4a8c2f6b913
Revises: b7d3e5f1a246
Create Date: 2026-11-26 16:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4a8c2f6b913"
down_revision: str | Sequence[str] | None = "b7d3e5f1a246"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive. A summary saved without it compares by time alone, as before."""
    with op.batch_alter_table("threads", schema=None) as batch_op:
        batch_op.add_column(sa.Column("summary_through_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("threads", schema=None) as batch_op:
        batch_op.drop_column("summary_through_id")
