"""The slice 5.2 migration (bot_tools, runs.requester_id) keeps today's behaviour: every existing
bot keeps every plugin in PLUGINS, through the connection 5.1 chose automatically, and runs a
person's message started act for that person. Run with Alembic on a scratch SQLite file, from the
revision before it, then down again."""

import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

BEFORE, AFTER = "e1c4d7a92b30", "8cf59be5197c"
API_DIR = Path(__file__).parent.parent


def _alembic(database: Path, *args: str) -> None:
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{database.as_posix()}",
        "DATABASE_URL_DIRECT": "",
        "PLUGINS": "demo,notes",  # ids only: the migration doesn't load plugins
        "ENVIRONMENT": "test",
    }
    done = subprocess.run(  # noqa: S603  (our own alembic, with a test database)
        [sys.executable, "-m", "alembic", *args], cwd=API_DIR, env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr[-3000:]


def _insert(db: sqlite3.Connection, table: str, **values: Any) -> str:
    """Insert a row, filling the other required columns with placeholders. Returns its id."""
    row = {"id": uuid.uuid4().hex, **values}
    for _, name, kind, not_null, default, _pk in db.execute(f"PRAGMA table_info({table})"):
        if name in row or not not_null or default is not None:
            continue
        kind = kind.upper()
        row[name] = (
            "2026-11-01 00:00:00.000000"
            if "DATETIME" in kind or "TIMESTAMP" in kind
            else 0
            if "INT" in kind or "BOOL" in kind
            else "{}"
            if "JSON" in kind
            else name
        )
    columns, marks = ", ".join(row), ", ".join("?" * len(row))
    db.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", list(row.values()))  # noqa: S608  (our names)
    return str(row["id"])


def _connection(db: sqlite3.Connection, org: str, kind: str, connector: str, at: str, **owner: Any) -> str:
    return _insert(
        db,
        "connections",
        org_id=org,
        connector_id=connector,
        owner_kind=kind,
        status=owner.pop("status", "active"),
        created_at=at,
        account_ref=uuid.uuid4().hex,
        **owner,
    )


def test_upgrade_gives_every_bot_its_plugins_through_the_51_choice_and_runs_their_requester(tmp_path: Path) -> None:
    database = tmp_path / "botdesk.db"
    _alembic(database, "upgrade", BEFORE)
    db = sqlite3.connect(database)
    user = _insert(db, "users", email="ali@acme.dev")
    org = _insert(db, "organizations")
    scout = _insert(db, "bots", org_id=org, created_by=user, handle="scout")
    inbox = _insert(db, "bots", org_id=org, created_by=user, handle="inbox")
    # demo: Scout has its own; the org has two (the older wins). A member's is never chosen.
    scouts_own = _connection(db, org, "bot", "demo", "2026-11-03 00:00:00", owner_bot_id=scout)
    older_org = _connection(db, org, "org", "demo", "2026-11-01 00:00:00")
    _connection(db, org, "org", "demo", "2026-11-02 00:00:00")
    _connection(db, org, "member", "demo", "2026-10-01 00:00:00", owner_user_id=user)
    _connection(db, org, "bot", "notes", "2026-10-01 00:00:00", owner_bot_id=inbox, status="revoked")
    thread = _insert(db, "threads", org_id=org, kind="dm", bot_id=scout, created_by=user)
    asked = _insert(db, "messages", org_id=org, thread_id=thread, author_type="user", author_id=user)
    reply = _insert(db, "messages", org_id=org, thread_id=thread, author_type="bot", author_id=scout)
    by_person = _insert(db, "runs", org_id=org, bot_id=scout, thread_id=thread, trigger_message_id=asked, hop=0)
    by_bot = _insert(db, "runs", org_id=org, bot_id=inbox, thread_id=thread, trigger_message_id=reply, hop=1)
    db.commit()
    db.close()

    _alembic(database, "upgrade", AFTER)
    db = sqlite3.connect(database)
    bindings = {
        (bot, plugin): (connection, enabled)
        for bot, plugin, connection, enabled in db.execute(
            "SELECT bot_id, plugin_id, connection_id, enabled FROM bot_tools"
        )
    }
    assert bindings == {
        (scout, "demo"): (scouts_own, 1),
        (scout, "notes"): (None, 1),
        (inbox, "demo"): (older_org, 1),
        (inbox, "notes"): (None, 1),  # its own is revoked
    }
    requesters = dict(db.execute("SELECT id, requester_id FROM runs"))
    assert requesters == {by_person: user, by_bot: None}
    db.close()

    _alembic(database, "downgrade", BEFORE)
    db = sqlite3.connect(database)
    assert db.execute("SELECT name FROM sqlite_master WHERE name = 'bot_tools'").fetchall() == []
    assert "requester_id" not in [column[1] for column in db.execute("PRAGMA table_info(runs)")]
    db.close()
