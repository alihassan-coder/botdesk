"""bot tools (bindings) and runs.requester_id (slice 5.2)

Revision ID: 8cf59be5197c
Revises: e1c4d7a92b30
Create Date: 2026-11-16 10:00:00.000000

"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8cf59be5197c"
down_revision: str | Sequence[str] | None = "e1c4d7a92b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive, with two backfills that keep today's behaviour:

    - every existing bot gets a binding, switched on, for each plugin in `PLUGINS`, through the
      connection 5.1 picked automatically (the bot's own active one on that connector, else the
      oldest active organization one, else none);
    - each run a person's message started acts for that person (`requester_id`).
    """
    op.create_table(
        "bot_tools",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("plugin_id", sa.String(length=80), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name=op.f("fk_bot_tools_bot_id_bots"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["connections.id"],
            name=op.f("fk_bot_tools_connection_id_connections"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_bot_tools_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_bot_tools_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bot_tools")),
        sa.UniqueConstraint("bot_id", "plugin_id", name="uq_bot_tools_bot_id_plugin_id"),
    )
    op.create_index(op.f("ix_bot_tools_org_id"), "bot_tools", ["org_id"], unique=False)
    op.create_index(op.f("ix_bot_tools_connection_id"), "bot_tools", ["connection_id"], unique=False)
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("requester_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_runs_requester_id_users"), "users", ["requester_id"], ["id"], ondelete="SET NULL"
        )

    _backfill_bindings()
    op.execute(
        "UPDATE runs SET requester_id = (SELECT messages.author_id FROM messages"
        " WHERE messages.id = runs.trigger_message_id AND messages.author_type = 'user')"
        " WHERE runs.hop = 0"
    )


def _backfill_bindings() -> None:
    from src.core.config import get_settings  # the same PLUGINS the API loads

    plugin_ids = get_settings().plugin_ids
    connection = op.get_bind()
    bots_table = sa.table(
        "bots", sa.column("id", sa.Uuid()), sa.column("org_id", sa.Uuid()), sa.column("created_by", sa.Uuid())
    )
    bots = connection.execute(sa.select(bots_table)).all()
    if not plugin_ids or not bots:
        return
    connections = sa.table(
        "connections",
        sa.column("id", sa.Uuid()),
        sa.column("org_id", sa.Uuid()),
        sa.column("connector_id", sa.String()),
        sa.column("owner_kind", sa.String()),
        sa.column("owner_bot_id", sa.Uuid()),
        sa.column("status", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    # Active bot- and org-owned connections, oldest first: the 5.1 automatic choice.
    active = connection.execute(
        sa.select(
            connections.c.id,
            connections.c.org_id,
            connections.c.connector_id,
            connections.c.owner_kind,
            connections.c.owner_bot_id,
        )
        .where(connections.c.status == "active", connections.c.owner_kind.in_(("bot", "org")))
        .order_by(connections.c.created_at, connections.c.id)
    ).all()
    bot_own: dict[tuple[object, str], object] = {}
    org_shared: dict[tuple[object, str], object] = {}
    for row in active:
        if row.owner_kind == "bot":
            bot_own.setdefault((row.owner_bot_id, row.connector_id), row.id)
        else:
            org_shared.setdefault((row.org_id, row.connector_id), row.id)
    now = datetime.now(UTC)
    rows = [
        {
            "id": uuid.uuid4(),
            "org_id": bot.org_id,
            "bot_id": bot.id,
            "plugin_id": plugin_id,
            "connection_id": bot_own.get((bot.id, plugin_id)) or org_shared.get((bot.org_id, plugin_id)),
            "enabled": True,
            "created_by": bot.created_by,
            "created_at": now,
            "updated_at": now,
        }
        for bot in bots
        for plugin_id in plugin_ids
    ]
    table = sa.table(
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
    op.bulk_insert(table, rows)


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_runs_requester_id_users"), type_="foreignkey")
        batch_op.drop_column("requester_id")
    op.drop_index(op.f("ix_bot_tools_connection_id"), table_name="bot_tools")
    op.drop_index(op.f("ix_bot_tools_org_id"), table_name="bot_tools")
    op.drop_table("bot_tools")
