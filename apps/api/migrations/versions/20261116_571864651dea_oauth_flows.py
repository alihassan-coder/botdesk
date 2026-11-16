"""oauth_flows: sign-ins with a provider in progress (slice 5.3)

Revision ID: 571864651dea
Revises: c3d81f2a6b57
Create Date: 2026-11-16 12:57:40.305228

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "571864651dea"
down_revision: str | Sequence[str] | None = "c3d81f2a6b57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Additive: one new table, no backfill."""
    op.create_table(
        "oauth_flows",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("code_verifier_encrypted", sa.Text(), nullable=False),
        sa.Column("connector_id", sa.String(length=80), nullable=False),
        sa.Column("owner_kind", sa.String(length=10), nullable=False),
        sa.Column("owner_bot_id", sa.Uuid(), nullable=True),
        sa.Column("access", sa.String(length=40), nullable=False),
        sa.Column("scopes", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_oauth_flows_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_bot_id"], ["bots.id"], name=op.f("fk_oauth_flows_owner_bot_id_bots"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_oauth_flows_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_flows")),
        sa.UniqueConstraint("state_hash", name=op.f("uq_oauth_flows_state_hash")),
    )
    op.create_index(op.f("ix_oauth_flows_expires_at"), "oauth_flows", ["expires_at"], unique=False)
    op.create_index(op.f("ix_oauth_flows_org_id"), "oauth_flows", ["org_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_oauth_flows_org_id"), table_name="oauth_flows")
    op.drop_index(op.f("ix_oauth_flows_expires_at"), table_name="oauth_flows")
    op.drop_table("oauth_flows")
