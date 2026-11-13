"""drop organization plan

BotDesk is free and open source with no paid plans (ADR 0008), so organizations have no plan.

Revision ID: 9f2d6c1b7a40
Revises: 1c690bab9e40
Create Date: 2026-11-13 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f2d6c1b7a40"
down_revision: str | Sequence[str] | None = "1c690bab9e40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.drop_column("plan")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("plan", sa.String(length=20), server_default="free", nullable=False))
