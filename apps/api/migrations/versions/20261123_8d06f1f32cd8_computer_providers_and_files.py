"""Bots' files (ADR 0017): the organization's storage provider, the files list, and the Files
plugin switched on for every bot.

Revision ID: 8d06f1f32cd8
Revises: e8b3c6d2a417
Create Date: 2026-11-23 16:30:57.259940

"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8d06f1f32cd8"
down_revision: str | Sequence[str] | None = "e8b3c6d2a417"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FILES = "files"


def upgrade() -> None:
    """Additive. No `computer_providers` row means Local, so nothing changes for anyone until an
    admin chooses storage. Every bot gets the Files plugin switched on (new bots get it from
    `bot_service.create_bot`)."""
    op.create_table(
        "computer_providers",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column(
            "config", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("secret_hint", sa.String(length=8), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_computer_providers_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_computer_providers_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_computer_providers")),
        sa.UniqueConstraint("org_id", "kind", name="uq_computer_providers_org_id_kind"),
    )
    op.create_table(
        "files",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=True),
        sa.Column("path", sa.String(length=300), nullable=False),
        sa.Column("storage_key", sa.String(length=600), nullable=False),
        sa.Column("storage", sa.String(length=400), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name=op.f("fk_files_bot_id_bots"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_files_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name=op.f("fk_files_run_id_runs"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_files_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
    )
    op.create_index(
        "uq_files_org_id_bot_id_path",
        "files",
        ["org_id", "bot_id", "path"],
        unique=True,
        postgresql_where=sa.text("bot_id IS NOT NULL"),
        sqlite_where=sa.text("bot_id IS NOT NULL"),
    )
    op.create_index(
        "uq_files_org_id_shared_path",
        "files",
        ["org_id", "path"],
        unique=True,
        postgresql_where=sa.text("bot_id IS NULL"),
        sqlite_where=sa.text("bot_id IS NULL"),
    )
    _backfill_files_bindings()


def _backfill_files_bindings() -> None:
    """A `files` binding, switched on with no connection, for every bot that has none."""
    connection = op.get_bind()
    bots = sa.table(
        "bots", sa.column("id", sa.Uuid()), sa.column("org_id", sa.Uuid()), sa.column("created_by", sa.Uuid())
    )
    bot_tools = sa.table(
        "bot_tools",
        sa.column("id", sa.Uuid()),
        sa.column("org_id", sa.Uuid()),
        sa.column("bot_id", sa.Uuid()),
        sa.column("plugin_id", sa.String()),
        sa.column("connection_id", sa.Uuid()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_by", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    has_files = sa.exists().where(bot_tools.c.bot_id == bots.c.id, bot_tools.c.plugin_id == FILES)
    missing = connection.execute(sa.select(bots.c.id, bots.c.org_id, bots.c.created_by).where(~has_files)).all()
    if not missing:
        return
    now = datetime.now(UTC)
    op.bulk_insert(
        bot_tools,
        [
            {
                "id": uuid.uuid4(),
                "org_id": bot.org_id,
                "bot_id": bot.id,
                "plugin_id": FILES,
                "connection_id": None,
                "enabled": True,
                "created_by": bot.created_by,
                "created_at": now,
                "updated_at": now,
            }
            for bot in missing
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM bot_tools WHERE plugin_id = :files").bindparams(files=FILES))
    op.drop_index("uq_files_org_id_shared_path", table_name="files")
    op.drop_index("uq_files_org_id_bot_id_path", table_name="files")
    op.drop_table("files")
    op.drop_table("computer_providers")
