"""organization default security level

Revision ID: 381735fe703b
Revises: 9f2d6c1b7a40
Create Date: 2026-11-15 13:11:35.875890

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "381735fe703b"
down_revision: str | Sequence[str] | None = "9f2d6c1b7a40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """New bots start at the org's default level. Existing orgs get the old fixed default."""
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "default_security_level",
                sa.String(length=30),
                server_default=sa.text("'ask-before-acting'"),
                nullable=False,
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.drop_column("default_security_level")
