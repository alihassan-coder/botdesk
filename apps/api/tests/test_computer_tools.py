"""The Computer plugin's tools (ADR 0020 §4) through the real tool pipeline: what asks and what
doesn't, approving an edited command, what a command gives back, taint, a lost answer, and copying
files. Orgo is a fake (tests/orgo_fake.py)."""

import base64
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from src.models import File, Run, ToolExecution
from src.models.bot import SecurityLevel
from src.plugins.registry import ToolRegistry
from src.runtime import tool_pipeline
from src.runtime.reporter import RunReporter
from src.runtime.runner import RunManager
from src.runtime.tool_pipeline import ExecuteDeps, NeedsAttention, ToolCallRequest, ToolOutcome
from src.services.tool_execution_service import Recorded, RunRef
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up
from tests.orgo_fake import HOST, KEY, FakeOrgo


@dataclass
class Coder:
    """A cloud bot at work: one (never started) run in its DM, its organization's Orgo key saved."""

    app: FastAPI
    client: httpx.AsyncClient
    org: str
    run: RunRef
    orgo: FakeOrgo

    @property
    def runs(self) -> RunManager:
        runs: RunManager = self.app.state.runs
        return runs

    @property
    def registry(self) -> ToolRegistry:
        return self.runs.registry

    async def record(
        self, tool: str, args: dict[str, Any], *, level: SecurityLevel = "ask-before-acting", tainted: bool = False
    ) -> tuple[str, Recorded]:
        call = tool_pipeline.prepare(
            self.registry, ToolCallRequest(f"call-{uuid.uuid4().hex[:6]}", tool, args), level=level, tainted=tainted
        )
        async with self.runs.sessionmaker() as db:
            recorded = await tool_pipeline.record(
                db, self.run, call, tainted=tainted, approval_expiry=timedelta(hours=1)
            )
            await db.commit()
        return call.decision, recorded

    async def execute(self, recorded: Recorded) -> ToolOutcome:
        reporter = RunReporter(
            self.runs.sessionmaker, self.runs.bus, self.run.org_id, self.run.thread_id, self.run.run_id
        )
        deps = ExecuteDeps(self.runs.sessionmaker, self.registry, reporter, self.run, timeout_seconds=5)
        return await tool_pipeline.execute(deps, recorded.execution.id)

    async def call(self, tool: str, **args: Any) -> dict[str, Any]:
        """Run a tool that doesn't ask, and give back what the model reads (as JSON)."""
        decision, recorded = await self.record(tool, args, level="autonomous")
        assert decision == "auto"
        await self.execute(recorded)
        async with self.runs.sessionmaker() as db:
            row = await db.get(ToolExecution, recorded.execution.id)
        assert row is not None
        assert row.status == "succeeded", row.error
        return row.result or {}


@pytest.fixture
async def coder(providers: FakeProviders) -> AsyncIterator[Coder]:
    orgo = FakeOrgo()
    providers.answer(HOST, handler=orgo.handle)
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        app.state.runs.computers.poll_seconds = 0
        me = await sign_up(client)
        org_id = me["organizations"][0]["id"]
        org = f"/api/v1/orgs/{org_id}"
        assert (await client.put(f"{org}/computer-provider", json={"provider": "orgo", "apiKey": KEY})).is_success
        bot = (await client.post(f"{org}/bots", json={"name": "Coder"})).json()
        assert (await client.patch(f"{org}/bots/{bot['id']}", json={"computer": "cloud"})).is_success
        thread = (await client.post(f"{org}/threads/dm", json={"botId": bot["id"]})).json()
        sent = (await client.post(f"{org}/threads/{thread['id']}/messages", json={"text": "Fix the bug"})).json()
        run = RunRef(
            run_id=uuid.UUID(sent["runIds"][0]),
            org_id=uuid.UUID(org_id),
            thread_id=uuid.UUID(thread["id"]),
            bot_id=uuid.UUID(bot["id"]),
        )
        yield Coder(app=app, client=client, org=org, run=run, orgo=orgo)


async def test_inspect_runs_without_asking_and_starts_the_computer_on_first_use(coder: Coder) -> None:
    coder.orgo.bash = lambda command: {"output": "src\ntests\n", "exit_code": 0, "success": True}
    decision, recorded = await coder.record("computer.inspect", {"command": "ls", "cwd": "~/app"})
    assert decision == "auto"  # at Ask before acting: reading never asks

    outcome = await coder.execute(recorded)

    assert coder.orgo.made() == 1
    assert coder.orgo.commands == ["cd -- ~/app || exit 1\nls"]
    assert outcome.tainted  # the computer's output is outside text
    assert outcome.text.startswith('<untrusted-content source="computer.inspect">')
    assert '"exitCode": 0' in outcome.text and '"cwd": "~/app"' in outcome.text
    async with coder.runs.sessionmaker() as db:
        run = await db.get(Run, coder.run.run_id)
    assert run is not None and run.tainted


async def test_inspect_refuses_a_command_that_could_change_something(coder: Coder) -> None:
    _, recorded = await coder.record("computer.inspect", {"command": "ls; rm -rf ~"})
    outcome = await coder.execute(recorded)
    assert outcome.text.startswith("The tool failed: Only one command") and "computer.run" in outcome.text
    assert coder.orgo.commands == [] and coder.orgo.made() == 0  # nothing reached the computer


async def test_run_asks_first_and_runs_the_command_as_approved(coder: Coder) -> None:
    decision, recorded = await coder.record("computer.run", {"command": "npm test"})
    assert decision == "ask"
    assert recorded.approval is not None

    (approval,) = (await coder.client.get(f"{coder.org}/approvals")).json()
    assert approval["summary"] == "Run `npm test` on the bot's computer"
    command = approval["argsSchema"]["properties"]["command"]
    assert command["maxLength"] == 8000  # long: the card shows the whole command, editable
    assert approval["preview"][0] == {"label": "Command", "value": "npm test"}

    edited = {"command": "npm test -- --runInBand", "cwd": "~/app", "timeout": 200}
    decided = await coder.client.post(
        f"{coder.org}/approvals/{approval['id']}/decide", json={"decision": "approve", "editedArgs": edited}
    )
    assert decided.status_code == 200, decided.text
    coder.orgo.bash = lambda command: {"output": "Tests: 3 failed\n", "exit_code": 1, "success": False}

    outcome = await coder.execute(recorded)

    assert coder.orgo.commands == ["cd -- ~/app || exit 1\nnpm test -- --runInBand"]
    (_, _, sent) = next(call for call in coder.orgo.calls if call[1].endswith("/bash"))
    assert sent["timeout"] == 200
    assert '"exitCode": 1' in outcome.text and "Tests: 3 failed" in outcome.text  # a failing exit is a result


async def test_a_long_output_keeps_its_start_and_its_end(coder: Coder) -> None:
    coder.orgo.bash = lambda command: {"output": "a" * 10_000 + "b" * 10_000, "exit_code": 0, "success": True}
    result = await coder.call("computer.run", command="make build")
    output = result["output"]
    assert output.startswith("a" * 8192) and output.endswith("b" * 8192)
    assert "… 3616 bytes cut …" in output
    assert isinstance(result["seconds"], float) and result["cwd"] == "~"


async def test_a_command_whose_answer_was_lost_stops_the_run_for_a_person(coder: Coder) -> None:
    def lost(command: str) -> httpx.Response:
        return httpx.Response(502, json={"error": "Bad gateway"})

    coder.orgo.bash = lost
    _, recorded = await coder.record("computer.run", {"command": "git push"}, level="autonomous")
    with pytest.raises(NeedsAttention, match="may have been done"):
        await coder.execute(recorded)


async def test_orgo_out_of_credit_fails_the_call_cleanly(coder: Coder) -> None:
    coder.orgo.refuse[("POST", "/computers")] = (402, {"error": "insufficient_credit"})
    _, recorded = await coder.record("computer.run", {"command": "ls"}, level="autonomous")
    outcome = await coder.execute(recorded)
    assert outcome.text == "The tool failed: Orgo says the account is out of credit. " + (
        "An owner or admin can add credit at orgo.ai, then try again."
    )
    assert KEY not in outcome.text


async def test_without_the_organizations_key_the_tools_say_who_can_add_it(coder: Coder) -> None:
    assert (await coder.client.delete(f"{coder.org}/computer-provider")).status_code == 204
    _, recorded = await coder.record("computer.inspect", {"command": "ls"})
    outcome = await coder.execute(recorded)
    assert outcome.text == "The tool failed: An owner or admin can add an Orgo key in Settings → Computers."


async def test_a_computer_stopped_outside_botdesk_is_started_again(coder: Coder) -> None:
    await coder.call("computer.inspect", command="pwd")
    coder.orgo.computers["pc-1"]["status"] = "stopped"  # stopped in Orgo's dashboard

    await coder.call("computer.inspect", command="pwd")

    assert coder.orgo.called("POST", "/computers/pc-1/start") == 1 and len(coder.orgo.commands) == 2


async def test_apps_logs_and_a_preview_link(coder: Coder) -> None:
    decision, _ = await coder.record("computer.start_app", {"name": "web", "command": "npm run dev"})
    assert decision == "ask"
    started = await coder.call("computer.start_app", name="web", command="npm run dev -- --host 0.0.0.0", port=3000)
    assert (started["name"], started["port"], started["status"]) == ("web", 3000, "running")
    _, _, body = next(call for call in coder.orgo.calls if call[:2] == ("POST", "/computers/pc-1/services"))
    assert body == {"name": "web", "command": "npm run dev -- --host 0.0.0.0", "restart": "on-failure", "port": 3000}

    replaced = await coder.call("computer.start_app", name="web", command="npm start", port=3000)
    assert replaced["status"] == "running" and len(coder.orgo.apps["pc-1"]) == 1  # the same name replaces it

    logs = await coder.call("computer.app_logs", name="web", lines=50)
    assert logs["log"] == "listening (50 lines asked)\n"

    decision, _ = await coder.record("computer.preview", {"port": 3000})
    assert decision == "ask"  # a link leaves the computer: external-send
    link = await coder.call("computer.preview", port=3000)
    assert link["url"] == "https://botdesk-coder-a2b3.web.orgo.dev" and link["access"] == "team"
    assert (await coder.call("computer.preview", port=3000))["url"] == link["url"]  # made once
    assert len(coder.orgo.previews["pc-1"]) == 1

    view = (await coder.client.get(f"{coder.org}/bots/{coder.run.bot_id}/computer")).json()
    assert view["apps"] == [{"name": "web", "port": 3000, "status": "running"}]
    assert view["previews"] == [{"url": link["url"], "port": 3000, "access": "team"}]

    assert (await coder.call("computer.stop_app", name="web")) == {"stopped": "web"}
    _, recorded = await coder.record("computer.app_logs", {"name": "web"})
    assert "There's no app called web" in (await coder.execute(recorded)).text


async def test_reserved_ports_are_refused_before_anything_runs(coder: Coder) -> None:
    call = tool_pipeline.prepare(
        coder.registry, ToolCallRequest("c1", "computer.preview", {"port": 5901}), level="autonomous", tainted=False
    )
    assert call.decision == "invalid" and call.refusal is not None


async def test_open_shows_a_page_on_the_screen(coder: Coder) -> None:
    decision, _ = await coder.record("computer.open", {"url": "http://localhost:3000"})
    assert decision == "auto"
    _, tainted = await coder.record("computer.open", {"url": "http://localhost:3000"}, tainted=True)
    assert tainted.approval is not None  # open egress in a tainted run asks

    opened = await coder.call("computer.open", url="http://localhost:3000")
    assert opened["opened"] == "http://localhost:3000"
    assert "DISPLAY=:0" in coder.orgo.commands[-1] and " http://localhost:3000 " in coder.orgo.commands[-1]
    await coder.call("computer.open", url="https://example.com/?q=a b;rm")
    assert "'https://example.com/?q=a b;rm'" in coder.orgo.commands[-1]  # quoted: never run as a command


async def test_a_screenshot_goes_to_the_bots_files(coder: Coder) -> None:
    saved = await coder.call("computer.screenshot")
    assert saved["path"].startswith("screenshots/computer-") and saved["path"].endswith(".png")
    assert saved["type"] == "image/png"
    async with coder.runs.sessionmaker() as db:
        file = await db.scalar(select(File).where(File.path == saved["path"]))
    assert file is not None and file.bot_id == coder.run.bot_id


async def test_files_copy_to_and_from_the_computer(coder: Coder) -> None:
    await coder.call("files.save", path="notes/todo.txt", text="ship it\n")
    written: dict[str, str] = {}

    def shell(command: str) -> dict[str, Any]:
        if command.startswith("printf %s "):
            chunk, _, spool = command.removeprefix("printf %s ").partition(" >> ")
            written[spool] = written.get(spool, "") + chunk
        if command.startswith("mkdir -p"):
            return {"output": f"{len(base64.b64decode(next(iter(written.values()))))}\n", "exit_code": 0}
        if command.startswith("stat -c %s"):
            return {"output": "11\n", "exit_code": 0}
        if command.startswith("dd if="):
            return {"output": base64.b64encode(b"hello world").decode(), "exit_code": 0}
        return {"output": "", "exit_code": 0}

    coder.orgo.bash = shell
    uploaded = await coder.call("computer.upload", path="notes/todo.txt")
    assert uploaded == {"uploaded": "notes/todo.txt", "to": "~/todo.txt", "size": 8}
    assert base64.b64decode(next(iter(written.values()))) == b"ship it\n"
    assert "> ~/todo.txt &&" in coder.orgo.commands[-1]

    downloaded = await coder.call("computer.download", path="~/app/report.txt")
    assert downloaded["path"] == "downloads/report.txt" and downloaded["size"] == 11
    read = await coder.call("files.read", path="downloads/report.txt")
    assert read["text"] == "hello world"


async def test_a_file_too_big_to_copy_is_refused(coder: Coder) -> None:
    coder.orgo.bash = lambda command: {"output": str(11 * 1024 * 1024), "exit_code": 0}
    _, recorded = await coder.record("computer.download", {"path": "~/big.iso"})
    assert "files up to 10 MB are copied" in (await coder.execute(recorded)).text
