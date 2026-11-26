"""Chat history (ADR 0019): organizations choose summaries and how long messages are kept; chats
keep a running summary of their older messages.

Revision ID: b7d3e5f1a246
Revises: 9a4c1e7b2d38
Create Date: 2026-11-26 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d3e5f1a246"
down_revision: str | Sequence[str] | None = "9a4c1e7b2d38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive: summaries start on, messages are kept forever (as before), no chat has a summary yet."""
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("history_summaries", sa.Boolean(), server_default=sa.true(), nullable=False))
        batch_op.add_column(sa.Column("history_retention_days", sa.Integer(), nullable=True))
    with op.batch_alter_table("threads", schema=None) as batch_op:
        batch_op.add_column(sa.Column("summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("summary_through", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("summary_tainted", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("threads", schema=None) as batch_op:
        batch_op.drop_column("summary_tainted")
        batch_op.drop_column("summary_through")
        batch_op.drop_column("summary")
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.drop_column("history_retention_days")
        batch_op.drop_column("history_summaries")
