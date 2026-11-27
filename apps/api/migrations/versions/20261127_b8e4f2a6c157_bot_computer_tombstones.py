"""A removed bot's cloud computer stays as a tombstone until Orgo confirms it's deleted
(ADR 0020 §3): `bot_computers.bot_id` may be empty, and removing a bot empties it instead of
deleting the row.

Revision ID: b8e4f2a6c157
Revises: f3c8a1d5e902
Create Date: 2026-11-27 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e4f2a6c157"
down_revision: str | Sequence[str] | None = "f3c8a1d5e902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK = "fk_bot_computers_bot_id_bots"


def upgrade() -> None:
    """No data changes: every row still has its bot."""
    with op.batch_alter_table("bot_computers", schema=None) as batch_op:
        batch_op.alter_column("bot_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.drop_constraint(FK, type_="foreignkey")
        batch_op.create_foreign_key(FK, "bots", ["bot_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    """Tombstones are dropped (their computers may still be at Orgo: delete them there)."""
    op.execute(sa.text("DELETE FROM bot_computers WHERE bot_id IS NULL"))
    with op.batch_alter_table("bot_computers", schema=None) as batch_op:
        batch_op.drop_constraint(FK, type_="foreignkey")
        batch_op.create_foreign_key(FK, "bots", ["bot_id"], ["id"], ondelete="CASCADE")
        batch_op.alter_column("bot_id", existing_type=sa.Uuid(), nullable=False)
