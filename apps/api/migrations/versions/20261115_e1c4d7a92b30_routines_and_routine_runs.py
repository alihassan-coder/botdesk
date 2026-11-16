"""routines and routine runs (slice 4: routines that really run)

Revision ID: e1c4d7a92b30
Revises: b7f3a9c1d2e4
Create Date: 2026-11-15 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1c4d7a92b30"
down_revision: str | Sequence[str] | None = "b7f3a9c1d2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive: two new tables."""
    op.create_table(
        "routines",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("cron", sa.String(length=120), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("security_level", sa.String(length=30), nullable=True),
        sa.Column("disabled_reason", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name=op.f("fk_routines_bot_id_bots"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_routines_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_routines_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_routines")),
    )
    op.create_index(op.f("ix_routines_org_id"), "routines", ["org_id"], unique=False)
    op.create_index(op.f("ix_routines_bot_id"), "routines", ["bot_id"], unique=False)
    op.create_index("ix_routines_enabled_next_run_at", "routines", ["enabled", "next_run_at"], unique=False)
    op.create_table(
        "routine_runs",
        sa.Column("routine_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["routine_id"], ["routines.id"], name=op.f("fk_routine_runs_routine_id_routines"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name=op.f("fk_routine_runs_run_id_runs"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_routine_runs")),
        sa.UniqueConstraint("run_id", name=op.f("uq_routine_runs_run_id")),
    )
    op.create_index("ix_routine_runs_routine_id_started_at", "routine_runs", ["routine_id", "started_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_routine_runs_routine_id_started_at", table_name="routine_runs")
    op.drop_table("routine_runs")
    op.drop_index("ix_routines_enabled_next_run_at", table_name="routines")
    op.drop_index(op.f("ix_routines_bot_id"), table_name="routines")
    op.drop_index(op.f("ix_routines_org_id"), table_name="routines")
    op.drop_table("routines")
