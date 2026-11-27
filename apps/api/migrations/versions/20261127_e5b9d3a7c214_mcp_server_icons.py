"""MCP servers keep their own icon (from the handshake's serverInfo.icons) as a data: URI.

Revision ID: e5b9d3a7c214
Revises: d4a8c2f6b913
Create Date: 2026-11-27 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b9d3a7c214"
down_revision: str | Sequence[str] | None = "d4a8c2f6b913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive: servers get their icon the next time they're refreshed or signed in to."""
    with op.batch_alter_table("mcp_servers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("icon", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mcp_servers", schema=None) as batch_op:
        batch_op.drop_column("icon")
