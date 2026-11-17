"""trigger_subscriptions: a bot reacting to new email (slice 6.3)

Revision ID: e5a9c3f71d20
Revises: b7d2f4a9c615
Create Date: 2026-11-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5a9c3f71d20"
down_revision: str | Sequence[str] | None = "b7d2f4a9c615"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXED = ("org_id", "subscriber_id", "connection_id")


def upgrade() -> None:
    """Additive: one new table."""
    op.create_table(
        "trigger_subscriptions",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("binding_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(length=80), nullable=False),
        sa.Column("subscriber_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("cursor", sa.String(length=200), nullable=True),
        sa.Column(
            "seen", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["bot_tools.id"],
            name=op.f("fk_trigger_subscriptions_binding_id_bot_tools"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["connections.id"],
            name=op.f("fk_trigger_subscriptions_connection_id_connections"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_trigger_subscriptions_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscriber_id"],
            ["users.id"],
            name=op.f("fk_trigger_subscriptions_subscriber_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trigger_subscriptions")),
        sa.UniqueConstraint("binding_id", "trigger", name="uq_trigger_subscriptions_binding_id_trigger"),
    )
    with op.batch_alter_table("trigger_subscriptions", schema=None) as batch_op:
        for column in INDEXED:
            batch_op.create_index(batch_op.f(f"ix_trigger_subscriptions_{column}"), [column], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("trigger_subscriptions", schema=None) as batch_op:
        for column in INDEXED:
            batch_op.drop_index(batch_op.f(f"ix_trigger_subscriptions_{column}"))
    op.drop_table("trigger_subscriptions")
