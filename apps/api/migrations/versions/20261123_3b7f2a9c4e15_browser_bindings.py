"""Bots' Local browsers (ADR 0017 step 2): the Browser plugin switched on for every bot.

Revision ID: 3b7f2a9c4e15
Revises: 8d06f1f32cd8
Create Date: 2026-11-23 18:40:00

"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b7f2a9c4e15"
down_revision: str | Sequence[str] | None = "8d06f1f32cd8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BROWSER = "browser"


def upgrade() -> None:
    """Data only: every bot gets the Browser plugin switched on (new bots get it from
    `bot_service.create_bot`). Its Tools tab can switch it off."""
    _backfill_browser_bindings()


def _backfill_browser_bindings() -> None:
    """A `browser` binding, switched on with no connection, for every bot that has none."""
    connection = op.get_bind()
    bots = sa.table(
        "bots", sa.column("id", sa.Uuid()), sa.column("org_id", sa.Uuid()), sa.column("created_by", sa.Uuid())
    )
    bot_tools = sa.table(
        "bot_tools",
        sa.column("id", sa.Uuid()),
        sa.column("org_id", sa.Uuid()),
        sa.column("bot_id", sa.Uuid()),
        sa.column("plugin_id", sa.String()),
        sa.column("connection_id", sa.Uuid()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_by", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    has_browser = sa.exists().where(bot_tools.c.bot_id == bots.c.id, bot_tools.c.plugin_id == BROWSER)
    missing = connection.execute(sa.select(bots.c.id, bots.c.org_id, bots.c.created_by).where(~has_browser)).all()
    if not missing:
        return
    now = datetime.now(UTC)
    op.bulk_insert(
        bot_tools,
        [
            {
                "id": uuid.uuid4(),
                "org_id": bot.org_id,
                "bot_id": bot.id,
                "plugin_id": BROWSER,
                "connection_id": None,
                "enabled": True,
                "created_by": bot.created_by,
                "created_at": now,
                "updated_at": now,
            }
            for bot in missing
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM bot_tools WHERE plugin_id = :browser").bindparams(browser=BROWSER))
