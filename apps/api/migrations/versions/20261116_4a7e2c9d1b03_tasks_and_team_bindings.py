"""tasks (handoffs, ADR 0014) and the Team plugin's bindings

Revision ID: 4a7e2c9d1b03
Revises: c3d81f2a6b57
Create Date: 2026-11-16 15:00:00.000000

"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4a7e2c9d1b03"
down_revision: str | Sequence[str] | None = "c3d81f2a6b57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEAM = "team"


def upgrade() -> None:
    """Additive. The new run status `waiting_handoff` needs no change (`runs.status` is a plain
    string), and a child run's level cap reuses `runs.security_level`. Every bot gets the Team
    plugin switched on (new bots get it from `bot_service.create_bot`)."""
    op.create_table(
        "tasks",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("parent_run_id", sa.Uuid(), nullable=False),
        sa.Column("tool_call_id", sa.String(length=120), nullable=False),
        sa.Column("from_bot_id", sa.Uuid(), nullable=True),
        sa.Column("to_bot_id", sa.Uuid(), nullable=False),
        sa.Column("child_run_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("requester_id", sa.Uuid(), nullable=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("result_message_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=20), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["child_run_id"], ["runs.id"], name=op.f("fk_tasks_child_run_id_runs"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["from_bot_id"], ["bots.id"], name=op.f("fk_tasks_from_bot_id_bots"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name=op.f("fk_tasks_message_id_messages"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_tasks_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_run_id"], ["runs.id"], name=op.f("fk_tasks_parent_run_id_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"], ["users.id"], name=op.f("fk_tasks_requester_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["result_message_id"],
            ["messages.id"],
            name=op.f("fk_tasks_result_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["threads.id"], name=op.f("fk_tasks_thread_id_threads"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["to_bot_id"], ["bots.id"], name=op.f("fk_tasks_to_bot_id_bots"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
        sa.UniqueConstraint("child_run_id", name=op.f("uq_tasks_child_run_id")),
        sa.UniqueConstraint("parent_run_id", "tool_call_id", name="uq_tasks_parent_run_id_tool_call_id"),
    )
    op.create_index(op.f("ix_tasks_org_id"), "tasks", ["org_id"], unique=False)
    op.create_index("ix_tasks_parent_run_id_status", "tasks", ["parent_run_id", "status"], unique=False)
    op.create_index("ix_tasks_org_id_status", "tasks", ["org_id", "status"], unique=False)
    op.create_index("ix_tasks_status_deadline_at", "tasks", ["status", "deadline_at"], unique=False)
    _backfill_team_bindings()


def _backfill_team_bindings() -> None:
    """A `team` binding, switched on with no connection, for every bot that has none."""
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
    has_team = sa.exists().where(bot_tools.c.bot_id == bots.c.id, bot_tools.c.plugin_id == TEAM)
    missing = connection.execute(sa.select(bots.c.id, bots.c.org_id, bots.c.created_by).where(~has_team)).all()
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
                "plugin_id": TEAM,
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
    """Runs waiting for tasks can't wait without them: they're cancelled."""
    op.execute("UPDATE runs SET status = 'cancelled', finished_at = CURRENT_TIMESTAMP WHERE status = 'waiting_handoff'")
    op.execute(f"DELETE FROM bot_tools WHERE plugin_id = '{TEAM}'")  # noqa: S608  (a constant)
    op.drop_index("ix_tasks_status_deadline_at", table_name="tasks")
    op.drop_index("ix_tasks_org_id_status", table_name="tasks")
    op.drop_index("ix_tasks_parent_run_id_status", table_name="tasks")
    op.drop_index(op.f("ix_tasks_org_id"), table_name="tasks")
    op.drop_table("tasks")
