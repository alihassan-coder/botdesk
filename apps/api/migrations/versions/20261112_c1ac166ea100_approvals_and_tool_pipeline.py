"""approvals and tool pipeline

Revision ID: c1ac166ea100
Revises: 580aa371d791
Create Date: 2026-11-12 16:58:39.840423

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c1ac166ea100"
down_revision: str | Sequence[str] | None = "580aa371d791"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "approvals",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("tool_execution_id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("risk", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("tainted", sa.Boolean(), nullable=False),
        sa.Column("args", JSON, nullable=False),
        sa.Column("final_args", JSON, nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name=op.f("fk_approvals_bot_id_bots"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name=op.f("fk_approvals_decided_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_approvals_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name=op.f("fk_approvals_run_id_runs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["threads.id"], name=op.f("fk_approvals_thread_id_threads"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tool_execution_id"],
            ["tool_executions.id"],
            name=op.f("fk_approvals_tool_execution_id_tool_executions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
        sa.UniqueConstraint("tool_execution_id", name=op.f("uq_approvals_tool_execution_id")),
    )
    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.create_index("ix_approvals_org_id_status_created_at", ["org_id", "status", "created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_approvals_run_id"), ["run_id"], unique=False)

    # Server defaults only so rows that already exist get a value; the app always sets them.
    with op.batch_alter_table("tool_executions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("risk", sa.String(length=20), nullable=False, server_default="read"))
        batch_op.add_column(sa.Column("decision", sa.String(length=10), nullable=False, server_default="auto"))
        batch_op.add_column(sa.Column("decision_trace", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("args", JSON, nullable=False, server_default=sa.text("'{}'")))
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.alter_column(
            "status", existing_type=sa.VARCHAR(length=12), type_=sa.String(length=20), existing_nullable=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("tool_executions", schema=None) as batch_op:
        batch_op.alter_column(
            "status", existing_type=sa.String(length=20), type_=sa.VARCHAR(length=12), existing_nullable=False
        )
        batch_op.drop_column("started_at")
        batch_op.drop_column("args")
        batch_op.drop_column("decision_trace")
        batch_op.drop_column("decision")
        batch_op.drop_column("risk")

    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_approvals_run_id"))
        batch_op.drop_index("ix_approvals_org_id_status_created_at")
    op.drop_table("approvals")
