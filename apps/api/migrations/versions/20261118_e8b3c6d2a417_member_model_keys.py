"""provider_credentials.user_id: members' own model keys

Revision ID: e8b3c6d2a417
Revises: d5e1a7c3f920
Create Date: 2026-11-18 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8b3c6d2a417"
down_revision: str | Sequence[str] | None = "d5e1a7c3f920"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUILTIN = "uq_provider_credentials_org_id_builtin"
MEMBER = "uq_provider_credentials_org_id_user_id_provider"


def upgrade() -> None:
    """Additive: every existing key stays the organization's (`user_id` empty). One key per
    built-in provider per organization still holds for organization keys; a member gets one
    of their own per provider.

    The partial unique index is dropped before the batch step: on SQLite adding the foreign key
    copies the table, and an index copied without its WHERE would refuse an organization's
    second custom server."""
    op.drop_index(BUILTIN, table_name="provider_credentials")
    with op.batch_alter_table("provider_credentials", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f("ix_provider_credentials_user_id"), ["user_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_provider_credentials_user_id_users"), "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
    op.create_index(
        BUILTIN,
        "provider_credentials",
        ["org_id", "provider"],
        unique=True,
        postgresql_where=sa.text("provider <> 'custom' AND user_id IS NULL"),
        sqlite_where=sa.text("provider <> 'custom' AND user_id IS NULL"),
    )
    op.create_index(
        MEMBER,
        "provider_credentials",
        ["org_id", "user_id", "provider"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
        sqlite_where=sa.text("user_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Members' own keys are deleted: the old schema has nowhere to keep them. The partial
    indexes go first and come back last, for the same reason as in `upgrade`."""
    op.execute("DELETE FROM provider_credentials WHERE user_id IS NOT NULL")
    op.drop_index(MEMBER, table_name="provider_credentials")
    op.drop_index(BUILTIN, table_name="provider_credentials")
    with op.batch_alter_table("provider_credentials", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_provider_credentials_user_id_users"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_provider_credentials_user_id"))
        batch_op.drop_column("user_id")
    op.create_index(
        BUILTIN,
        "provider_credentials",
        ["org_id", "provider"],
        unique=True,
        postgresql_where=sa.text("provider <> 'custom'"),
        sqlite_where=sa.text("provider <> 'custom'"),
    )
