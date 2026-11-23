"""The Files tools a bot calls (ADR 0017 §4), through the app's own registry as a run calls them:
its folder, the shared one, text and other files, and the same rules as people's uploads."""

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from botdesk_plugin_sdk import ToolContext
from fastapi import FastAPI

from src.services.file_tools import ToolFailed
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up


@dataclass
class BotAtWork:
    app: FastAPI
    client: httpx.AsyncClient
    org: str
    bot: dict[str, Any]
    ctx: ToolContext

    async def call(self, tool: str, **args: Any) -> dict[str, Any]:
        registered = self.app.state.runs.registry.get(f"files.{tool}")
        assert registered is not None
        result: dict[str, Any] = await registered.spec.handler(registered.spec.args_model(**args), self.ctx)
        return result


@pytest.fixture
async def inbox_manager() -> AsyncIterator[BotAtWork]:
    """Inbox Manager in a run of its own (a DM message starts one; runs never start in tests)."""
    async with api_client(TEST_SETTINGS, FakeProviders()) as (app, client):
        me = await sign_up(client)
        org_id = me["organizations"][0]["id"]
        org = f"/api/v1/orgs/{org_id}"
        bot = (await client.post(f"{org}/bots", json={"name": "Inbox Manager"})).json()
        thread = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
        run_id = (await client.post(f"{org}/threads/{thread['id']}/messages", json={"text": "Hi"})).json()["runIds"][0]
        ctx = ToolContext(
            org_id=uuid.UUID(org_id),
            bot_id=uuid.UUID(bot["id"]),
            run_id=uuid.UUID(run_id),
            tool_call_id="call-1",
            idempotency_key=f"{run_id}:call-1",
            logger=logging.getLogger("test"),
        )
        yield BotAtWork(app, client, org, bot, ctx)


async def test_a_bot_saves_lists_and_reads_its_own_files(inbox_manager: BotAtWork) -> None:
    saved = await inbox_manager.call("save", path="reports/march.md", text="# March\nAll good.")
    assert saved["saved"] == "botdesk/inbox-manager/reports/march.md"

    listed = await inbox_manager.call("list")
    assert listed["folder"] == "botdesk/inbox-manager"
    assert [(f["path"], f["type"]) for f in listed["files"]] == [("reports/march.md", "text/markdown")]

    read = await inbox_manager.call("read", path="reports/march.md")
    assert read["text"] == "# March\nAll good."

    # People see what the bot saved, in the bot's Files.
    files = await inbox_manager.client.get(f"{inbox_manager.org}/files", params={"botId": inbox_manager.bot["id"]})
    assert [f["path"] for f in files.json()] == ["reports/march.md"]


async def test_long_text_comes_in_parts(inbox_manager: BotAtWork) -> None:
    await inbox_manager.call("save", path="long.txt", text="a" * 20_000 + "b" * 5)
    first = await inbox_manager.call("read", path="long.txt")
    assert (len(first["text"]), first["next_start"]) == (20_000, 20_000)
    rest = await inbox_manager.call("read", path="long.txt", start=first["next_start"])
    assert (rest["text"], "next_start" in rest) == ("bbbbb", False)


async def test_files_that_are_not_text_say_what_they_are(inbox_manager: BotAtWork) -> None:
    upload = {"file": ("logo.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    await inbox_manager.client.post(f"{inbox_manager.org}/files", data={"botId": inbox_manager.bot["id"]}, files=upload)
    read = await inbox_manager.call("read", path="logo.png")
    assert (read["type"], read["size"], "text" in read) == ("image/png", 8, False)


async def test_the_shared_folder_is_separate(inbox_manager: BotAtWork) -> None:
    await inbox_manager.call("save", path="brand.md", text="Be kind.", shared=True)
    assert (await inbox_manager.call("list"))["files"] == []
    shared = await inbox_manager.call("list", shared=True)
    assert (shared["folder"], [f["path"] for f in shared["files"]]) == ("botdesk/_shared", ["brand.md"])


async def test_deleting_and_missing_files(inbox_manager: BotAtWork) -> None:
    await inbox_manager.call("save", path="old.txt", text="x")
    assert (await inbox_manager.call("delete", path="old.txt")) == {"deleted": "old.txt"}
    with pytest.raises(ToolFailed, match=r"no file called old\.txt"):
        await inbox_manager.call("read", path="old.txt")


async def test_bots_follow_the_same_path_rules_as_people(inbox_manager: BotAtWork) -> None:
    with pytest.raises(ToolFailed, match="usable file path"):
        await inbox_manager.call("save", path="../other-bot/x.txt", text="x")
