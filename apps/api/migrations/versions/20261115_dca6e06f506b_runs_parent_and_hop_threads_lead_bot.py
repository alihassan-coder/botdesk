"""runs parent and hop, threads lead bot

Revision ID: dca6e06f506b
Revises: 381735fe703b
Create Date: 2026-11-15 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dca6e06f506b"
down_revision: str | Sequence[str] | None = "381735fe703b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Bots working together (ADR 0009). Additive: existing runs are hop 0 with no parent, and
    existing groups have no lead (they behave as before: a message with no mention gets no reply)."""
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("parent_run_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("hop", sa.Integer(), server_default=sa.text("0"), nullable=False))
        batch_op.create_index(batch_op.f("ix_runs_parent_run_id"), ["parent_run_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_runs_parent_run_id_runs"), "runs", ["parent_run_id"], ["id"], ondelete="SET NULL"
        )
    with op.batch_alter_table("threads", schema=None) as batch_op:
        batch_op.add_column(sa.Column("lead_bot_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_threads_lead_bot_id_bots"), "bots", ["lead_bot_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("threads", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_threads_lead_bot_id_bots"), type_="foreignkey")
        batch_op.drop_column("lead_bot_id")
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_runs_parent_run_id_runs"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_runs_parent_run_id"))
        batch_op.drop_column("hop")
        batch_op.drop_column("parent_run_id")
