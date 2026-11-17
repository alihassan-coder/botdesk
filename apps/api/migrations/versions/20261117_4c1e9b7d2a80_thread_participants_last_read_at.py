"""thread_participants.last_read_at: unread counts in the chat list

Revision ID: 4c1e9b7d2a80
Revises: 73107c948749
Create Date: 2026-11-17 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c1e9b7d2a80"
down_revision: str | Sequence[str] | None = "73107c948749"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive: one column. Existing participants count as having read everything up to now,
    so the first deploy doesn't light every chat up as unread."""
    op.add_column(
        "thread_participants",
        sa.Column("last_read_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("thread_participants", "last_read_at")
