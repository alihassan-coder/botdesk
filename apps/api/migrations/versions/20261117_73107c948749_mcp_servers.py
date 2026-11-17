"""mcp servers: an organization's remote MCP servers and their tool snapshots (slice 7.2)

Revision ID: 73107c948749
Revises: e5a9c3f71d20
Create Date: 2026-11-17 21:04:53.513719

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "73107c948749"
down_revision: str | Sequence[str] | None = "e5a9c3f71d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive: one new table."""
    op.create_table(
        "mcp_servers",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("short_id", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("auth_kind", sa.String(length=20), nullable=False),
        sa.Column("auth_header", sa.String(length=64), nullable=True),
        sa.Column("encrypted_auth", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column(
            "tools", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("tools_hash", sa.String(length=64), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_mcp_servers_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_mcp_servers_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_servers")),
        sa.UniqueConstraint("short_id", name=op.f("uq_mcp_servers_short_id")),
    )
    with op.batch_alter_table("mcp_servers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mcp_servers_org_id"), ["org_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("mcp_servers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mcp_servers_org_id"))
    op.drop_table("mcp_servers")
