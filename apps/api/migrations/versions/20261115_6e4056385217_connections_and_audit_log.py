"""connections and audit log

Revision ID: 6e4056385217
Revises: dca6e06f506b
Create Date: 2026-11-15 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6e4056385217"
down_revision: str | Sequence[str] | None = "dca6e06f506b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    """The connection platform (ADR 0010, slice 5.1). Additive: two new tables and two nullable
    columns; existing tool calls and approvals have no connection."""
    op.create_table(
        "connections",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("connector_id", sa.String(length=80), nullable=False),
        sa.Column("owner_kind", sa.String(length=10), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("owner_bot_id", sa.Uuid(), nullable=True),
        sa.Column("auth_type", sa.String(length=10), nullable=False),
        sa.Column("account_label", sa.String(length=200), nullable=False),
        sa.Column("account_ref", sa.String(length=255), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=True),
        sa.Column("scopes", JSON, nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("refresh_lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(owner_kind = 'member' AND owner_user_id IS NOT NULL AND owner_bot_id IS NULL)"
            " OR (owner_kind = 'bot' AND owner_bot_id IS NOT NULL AND owner_user_id IS NULL)"
            " OR (owner_kind = 'org' AND owner_user_id IS NULL AND owner_bot_id IS NULL)",
            name=op.f("ck_connections_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_connections_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_connections_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_bot_id"], ["bots.id"], name=op.f("fk_connections_owner_bot_id_bots"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], name=op.f("fk_connections_owner_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_connections")),
    )
    with op.batch_alter_table("connections", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_connections_org_id"), ["org_id"], unique=False)
        batch_op.create_index(
            "uq_connections_account",
            [
                "org_id",
                "connector_id",
                "owner_kind",
                sa.text("coalesce(owner_user_id, owner_bot_id, org_id)"),
                "account_ref",
            ],
            unique=True,
        )

    op.create_table(
        "audit_log",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("target_kind", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("details", JSON, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name=op.f("fk_audit_log_actor_user_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_audit_log_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.create_index("ix_audit_log_org_id_created_at", ["org_id", "created_at"], unique=False)

    for table in ("tool_executions", "approvals"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("connection_id", sa.Uuid(), nullable=True))
            batch_op.create_foreign_key(
                batch_op.f(f"fk_{table}_connection_id_connections"),
                "connections",
                ["connection_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    for table in ("approvals", "tool_executions"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(batch_op.f(f"fk_{table}_connection_id_connections"), type_="foreignkey")
            batch_op.drop_column("connection_id")
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_log_org_id_created_at")
    op.drop_table("audit_log")
    with op.batch_alter_table("connections", schema=None) as batch_op:
        batch_op.drop_index("uq_connections_account")
        batch_op.drop_index(batch_op.f("ix_connections_org_id"))
    op.drop_table("connections")
