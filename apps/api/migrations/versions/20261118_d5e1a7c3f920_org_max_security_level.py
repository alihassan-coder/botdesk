"""organizations.max_security_level: the organization's security level ceiling

Revision ID: d5e1a7c3f920
Revises: d4b8e1f0a372
Create Date: 2026-11-18 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e1a7c3f920"
down_revision: str | Sequence[str] | None = "d4b8e1f0a372"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive. Existing organizations get no ceiling ("autonomous"), so no run changes level."""
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("max_security_level", sa.String(length=30), server_default="autonomous", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.drop_column("max_security_level")
