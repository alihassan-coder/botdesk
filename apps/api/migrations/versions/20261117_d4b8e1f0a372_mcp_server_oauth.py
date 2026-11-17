"""mcp servers: OAuth sign-in settings (slice 7.3)

Revision ID: d4b8e1f0a372
Revises: 73107c948749
Create Date: 2026-11-17 23:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4b8e1f0a372"
down_revision: str | Sequence[str] | None = "73107c948749"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive: one nullable column. The per-tool review state (slice 7.4) lives in the existing
    `tools` snapshot JSON; entries saved before it read as approved, offered, external-send."""
    op.add_column(
        "mcp_servers",
        sa.Column("oauth", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mcp_servers", "oauth")
