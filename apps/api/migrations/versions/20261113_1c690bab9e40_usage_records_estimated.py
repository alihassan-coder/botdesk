"""usage records estimated

Revision ID: 1c690bab9e40
Revises: 7d2c4e9a1b3f
Create Date: 2026-11-13 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1c690bab9e40"
down_revision: str | Sequence[str] | None = "7d2c4e9a1b3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("usage_records", sa.Column("estimated", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("usage_records", "estimated")
