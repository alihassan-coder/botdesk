"""memory scope in mem0 run_id

Memories used to carry the member scope only in `metadata.member`, which mem0 ignores when it
builds its extraction context. They now carry it in mem0's `run_id` entity key (see
`src/runtime/memory.py`). This copies `member` into `run_id` for rows saved before. Rows with
neither were never scoped and stay out of every scope.

mem0 creates its `bot_memories` table itself the first time memory is used, so there may be
nothing to migrate; this is a no-op then, and on SQLite.

Revision ID: 7d2c4e9a1b3f
Revises: 3e0c1566143b
Create Date: 2026-11-13 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d2c4e9a1b3f"
down_revision: str | Sequence[str] | None = "3e0c1566143b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_memories() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql" and sa.inspect(bind).has_table("bot_memories")


def upgrade() -> None:
    """Copy each memory's `member` into mem0's `run_id`."""
    if _has_memories():
        op.execute(
            """
            UPDATE bot_memories
            SET payload = payload || jsonb_build_object('run_id', payload->>'member')
            WHERE NOT payload ? 'run_id' AND payload->>'member' IS NOT NULL
            """
        )


def downgrade() -> None:
    """The old code ignores `run_id`; `member` is still there, so nothing to undo."""
