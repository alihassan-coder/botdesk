"""procrastinate job queue

Revision ID: b7f3a9c1d2e4
Revises: 6e4056385217
Create Date: 2026-11-15 20:00:00.000000

"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7f3a9c1d2e4"
down_revision: str | Sequence[str] | None = "6e4056385217"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# procrastinate's own schema, pinned to the version it shipped with (ADR 0013).
SCHEMA = Path(__file__).parent.parent / "sql" / "procrastinate-3.11.0.sql"

DROP = """
DROP TABLE IF EXISTS procrastinate_events, procrastinate_periodic_defers, procrastinate_jobs,
    procrastinate_workers CASCADE;
DO $$
DECLARE f record;
BEGIN
    FOR f IN SELECT p.oid::regprocedure AS sig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = current_schema() AND p.proname LIKE 'procrastinate\\_%'
    LOOP
        EXECUTE 'DROP FUNCTION IF EXISTS ' || f.sig || ' CASCADE';
    END LOOP;
END $$;
DROP TYPE IF EXISTS procrastinate_job_to_defer_v1, procrastinate_job_event_type, procrastinate_job_status CASCADE;
"""


def _run(sql: str) -> None:
    """Run a whole SQL script on the driver's cursor, with no parameters (so `%` is plain text
    and several statements are allowed)."""
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)  # type: ignore[union-attr]


def upgrade() -> None:
    """The job queue's tables, functions and triggers (Postgres only: on SQLite jobs run in the
    API process and nothing is saved)."""
    if op.get_bind().dialect.name != "postgresql":
        return
    _run(SCHEMA.read_text(encoding="utf-8"))


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    _run(DROP)
