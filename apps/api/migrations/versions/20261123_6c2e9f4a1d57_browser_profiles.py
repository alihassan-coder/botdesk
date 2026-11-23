"""Bots' browser profiles at cloud browser providers (ADR 0017 step 4).

Revision ID: 6c2e9f4a1d57
Revises: 3b7f2a9c4e15
Create Date: 2026-11-23 20:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c2e9f4a1d57"
down_revision: str | Sequence[str] | None = "3b7f2a9c4e15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive. The organization's browser provider is a `computer_providers` row of kind
    "browser" (no row: Local), so only the per-bot profiles need a table."""
    op.create_table(
        "browser_profiles",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("ref", sa.String(length=200), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["bots.id"], name=op.f("fk_browser_profiles_bot_id_bots"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_browser_profiles_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_browser_profiles")),
        sa.UniqueConstraint("bot_id", "provider", name="uq_browser_profiles_bot_id_provider"),
    )
    op.create_index(op.f("ix_browser_profiles_org_id"), "browser_profiles", ["org_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_browser_profiles_org_id"), table_name="browser_profiles")
    op.drop_table("browser_profiles")
