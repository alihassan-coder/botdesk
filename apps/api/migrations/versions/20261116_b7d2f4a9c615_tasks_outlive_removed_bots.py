"""tasks outlive a removed bot (to_bot_id SET NULL, the owner's name kept) and their FK indexes

Revision ID: b7d2f4a9c615
Revises: 4a7e2c9d1b03
Create Date: 2026-11-16 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d2f4a9c615"
down_revision: str | Sequence[str] | None = "4a7e2c9d1b03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXED = ("thread_id", "from_bot_id", "to_bot_id", "message_id")


def upgrade() -> None:
    """Removing a bot no longer deletes the tasks handed to it: `to_bot_id` becomes SET NULL
    (like `from_bot_id`), and the owner's name and handle are kept on the task, so a parent still
    waiting reads "Sales was removed" instead of losing the task. Indexes on the columns that
    deletes cascade through (a thread, a bot, a message) and that cards are looked up by."""
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("to_bot_name", sa.String(length=80), server_default="", nullable=False))
        batch_op.add_column(sa.Column("to_bot_handle", sa.String(length=64), server_default="", nullable=False))
        batch_op.drop_constraint(batch_op.f("fk_tasks_to_bot_id_bots"), type_="foreignkey")
        batch_op.alter_column("to_bot_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.create_foreign_key(
            batch_op.f("fk_tasks_to_bot_id_bots"), "bots", ["to_bot_id"], ["id"], ondelete="SET NULL"
        )
        for column in INDEXED:
            batch_op.create_index(batch_op.f(f"ix_tasks_{column}"), [column], unique=False)
    tasks = sa.table(
        "tasks",
        sa.column("to_bot_id", sa.Uuid()),
        sa.column("to_bot_name", sa.String()),
        sa.column("to_bot_handle", sa.String()),
    )
    bots = sa.table(
        "bots", sa.column("id", sa.Uuid()), sa.column("name", sa.String()), sa.column("handle", sa.String())
    )
    op.execute(
        tasks.update().values(
            to_bot_name=sa.select(bots.c.name).where(bots.c.id == tasks.c.to_bot_id).scalar_subquery(),
            to_bot_handle=sa.select(bots.c.handle).where(bots.c.id == tasks.c.to_bot_id).scalar_subquery(),
        )
    )


def downgrade() -> None:
    """Tasks whose owner was removed can't point at it again: they're deleted, as the old cascade
    would have done."""
    op.execute("DELETE FROM tasks WHERE to_bot_id IS NULL")
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        for column in reversed(INDEXED):
            batch_op.drop_index(batch_op.f(f"ix_tasks_{column}"))
        batch_op.drop_constraint(batch_op.f("fk_tasks_to_bot_id_bots"), type_="foreignkey")
        batch_op.alter_column("to_bot_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_tasks_to_bot_id_bots"), "bots", ["to_bot_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.drop_column("to_bot_handle")
        batch_op.drop_column("to_bot_name")
