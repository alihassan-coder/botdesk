"""The handoffs migration (ADR 0014): a `tasks` table, and every bot gets the Team plugin switched
on. Down again, runs waiting for tasks are cancelled and the Team bindings go. Alembic on a
scratch SQLite file."""

import sqlite3
from pathlib import Path

from tests.test_migration_bindings import _alembic, _insert

BEFORE, AFTER = "c3d81f2a6b57", "4a7e2c9d1b03"


def test_upgrade_adds_tasks_and_a_team_binding_for_every_bot_and_downgrade_undoes_it(tmp_path: Path) -> None:
    database = tmp_path / "botdesk.db"
    _alembic(database, "upgrade", BEFORE)
    db = sqlite3.connect(database)
    user = _insert(db, "users", email="ali@acme.dev")
    org = _insert(db, "organizations")
    chief = _insert(db, "bots", org_id=org, created_by=user, handle="chief")
    sales = _insert(db, "bots", org_id=org, created_by=user, handle="sales")
    _insert(db, "bot_tools", org_id=org, bot_id=chief, plugin_id="demo", enabled=1)
    thread = _insert(db, "threads", org_id=org, kind="dm", bot_id=chief, created_by=user)
    db.commit()
    db.close()

    _alembic(database, "upgrade", AFTER)
    db = sqlite3.connect(database)
    bindings = set(db.execute("SELECT bot_id, plugin_id, enabled, connection_id FROM bot_tools"))
    assert bindings == {(chief, "demo", 1, None), (chief, "team", 1, None), (sales, "team", 1, None)}
    columns = [column[1] for column in db.execute("PRAGMA table_info(tasks)")]
    assert {"parent_run_id", "tool_call_id", "child_run_id", "deadline_at", "error_code"} <= set(columns)
    waiting = _insert(db, "runs", org_id=org, bot_id=chief, thread_id=thread, status="waiting_handoff")
    done = _insert(db, "runs", org_id=org, bot_id=chief, thread_id=thread, status="succeeded")
    db.commit()
    db.close()

    _alembic(database, "downgrade", BEFORE)
    db = sqlite3.connect(database)
    assert db.execute("SELECT name FROM sqlite_master WHERE name = 'tasks'").fetchall() == []
    assert set(db.execute("SELECT bot_id, plugin_id FROM bot_tools")) == {(chief, "demo")}
    statuses = dict(db.execute("SELECT id, status FROM runs"))
    assert statuses == {waiting: "cancelled", done: "succeeded"}
    db.close()


KEEP = "b7d2f4a9c615"


def test_tasks_outlive_a_removed_bot_and_get_their_indexes_and_downgrade_drops_the_orphans(tmp_path: Path) -> None:
    database = tmp_path / "botdesk.db"
    _alembic(database, "upgrade", AFTER)
    db = sqlite3.connect(database)
    user = _insert(db, "users", email="ali@acme.dev")
    org = _insert(db, "organizations")
    chief = _insert(db, "bots", org_id=org, created_by=user, handle="chief", name="Chief")
    sales = _insert(db, "bots", org_id=org, created_by=user, handle="sales", name="Sales Outbound")
    research = _insert(db, "bots", org_id=org, created_by=user, handle="research", name="Research")
    thread = _insert(db, "threads", org_id=org, kind="dm", bot_id=chief, created_by=user)
    parent = _insert(db, "runs", org_id=org, bot_id=chief, thread_id=thread, status="waiting_handoff")
    common = {"org_id": org, "thread_id": thread, "parent_run_id": parent, "from_bot_id": chief, "status": "queued"}
    to_sales = _insert(db, "tasks", **common, tool_call_id="call_1", to_bot_id=sales)
    to_research = _insert(db, "tasks", **common, tool_call_id="call_2", to_bot_id=research)
    db.commit()
    db.close()

    _alembic(database, "upgrade", KEEP)
    db = sqlite3.connect(database)
    db.execute("PRAGMA foreign_keys=ON")
    names = dict((row[0], row[1:]) for row in db.execute("SELECT id, to_bot_name, to_bot_handle FROM tasks"))
    assert names == {to_sales: ("Sales Outbound", "sales"), to_research: ("Research", "research")}
    indexes = {row[1] for row in db.execute("PRAGMA index_list(tasks)")}
    assert {"ix_tasks_thread_id", "ix_tasks_from_bot_id", "ix_tasks_to_bot_id", "ix_tasks_message_id"} <= indexes
    db.execute("DELETE FROM bots WHERE id = ?", (sales,))
    db.commit()
    assert dict(db.execute("SELECT id, to_bot_id FROM tasks")) == {to_sales: None, to_research: research}
    db.close()

    _alembic(database, "downgrade", AFTER)
    db = sqlite3.connect(database)
    assert [row[0] for row in db.execute("SELECT id FROM tasks")] == [to_research]
    columns = {column[1] for column in db.execute("PRAGMA table_info(tasks)")}
    assert "to_bot_name" not in columns
    indexes = {row[1] for row in db.execute("PRAGMA index_list(tasks)")}
    assert "ix_tasks_to_bot_id" not in indexes and "ix_tasks_org_id" in indexes
    db.close()
