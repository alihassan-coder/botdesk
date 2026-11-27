"""Bots' cloud computers (ADR 0020): each bot's mode (browser or cloud), its computer, and the
Computer plugin switched on for every bot (its tools are offered only in cloud mode).

The organization's Orgo key is a `computer_providers` row of kind "computer" (the table ADR 0017
made for storage and browsers), so that table doesn't change.

Revision ID: f3c8a1d5e902
Revises: e5b9d3a7c214
Create Date: 2026-11-27 14:00:00

"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3c8a1d5e902"
down_revision: str | Sequence[str] | None = "e5b9d3a7c214"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMPUTER = "computer"


def upgrade() -> None:
    """Additive: every bot stays on its browser until someone switches it to cloud."""
    with op.batch_alter_table("bots", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("computer", sa.String(length=20), server_default=sa.text("'browser'"), nullable=False)
        )
    op.create_table(
        "bot_computers",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("remote_id", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cpu", sa.Float(), nullable=True),
        sa.Column("ram", sa.Integer(), nullable=True),
        sa.Column("region", sa.String(length=40), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name=op.f("fk_bot_computers_bot_id_bots"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_bot_computers_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bot_computers")),
        sa.UniqueConstraint("bot_id", name=op.f("uq_bot_computers_bot_id")),
    )
    with op.batch_alter_table("bot_computers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_bot_computers_org_id"), ["org_id"], unique=False)
    _backfill_computer_bindings()


def _backfill_computer_bindings() -> None:
    """A `computer` binding, switched on with no connection, for every bot that has none."""
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
    has_computer = sa.exists().where(bot_tools.c.bot_id == bots.c.id, bot_tools.c.plugin_id == COMPUTER)
    missing = connection.execute(sa.select(bots.c.id, bots.c.org_id, bots.c.created_by).where(~has_computer)).all()
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
                "plugin_id": COMPUTER,
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
    op.execute(sa.text("DELETE FROM bot_tools WHERE plugin_id = :computer").bindparams(computer=COMPUTER))
    with op.batch_alter_table("bot_computers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bot_computers_org_id"))
    op.drop_table("bot_computers")
    with op.batch_alter_table("bots", schema=None) as batch_op:
        batch_op.drop_column("computer")
