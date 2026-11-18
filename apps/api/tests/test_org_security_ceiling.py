"""The organization's security level ceiling (ADR 0004: the strictest of org, bot and routine wins).

Owners and admins set `maxSecurityLevel`. No bot may be set above it, the default for new bots
stays at or under it, and a run's effective level is the strictest of the ceiling, its bot's level
and the level the run started with: read when the run loads its context, and the ceiling again
before every tool call, so lowering it reaches runs already going. Routines, the Gmail trigger and
handoff children all go through the same path."""

import uuid
from typing import Any

import httpx
from sqlalchemy import select, update

from src.models import Organization, ToolExecution
from src.services import run_service
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up
from tests.test_gmail_trigger import INVOICE, ME, _on_and_baselined, _poll, _runs, history
from tests.test_handoffs import Org, handoff, org  # noqa: F401  (org is a fixture)
from tests.test_members import _invite, _sign_in
from tests.test_oauth import acme
from tests.test_routines import Team, team  # noqa: F401  (team is a fixture)

ORGS = "/api/v1/orgs"
ABOVE_THE_CEILING = (
    "This organization's highest security level is {level}. Owners and admins can raise it in Settings → Security."
)


async def _sara_joins(client: httpx.AsyncClient) -> str:
    """Ali owns the organization and Sara joins it as a member. Sara is signed in; returns the org's path."""
    ali = await sign_up(client, name="Ali", email="ali@acme.dev")
    org_id = ali["organizations"][0]["id"]
    token = await _invite(client, org_id, "sara@acme.dev")
    client.cookies.clear()
    await sign_up(client, name="Sara", email="sara@acme.dev")
    assert (await client.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200
    return f"{ORGS}/{org_id}"


async def _level(app: Any, run_id: uuid.UUID | str) -> str:
    async with app.state.sessionmaker() as db:
        return (await run_service.run_context(db, uuid.UUID(str(run_id)))).security_level


# Setting it


async def test_a_new_organization_has_no_ceiling_below_autonomous(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    saved = (await client.get(f"{ORGS}/{me['organizations'][0]['id']}")).json()
    assert saved["maxSecurityLevel"] == "autonomous"


async def test_owners_set_the_ceiling(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    org_id = me["organizations"][0]["id"]

    response = await client.patch(f"{ORGS}/{org_id}", json={"maxSecurityLevel": "ask-before-acting"})

    assert response.status_code == 200, response.text
    assert response.json()["maxSecurityLevel"] == "ask-before-acting"
    assert (await client.get(f"{ORGS}/{org_id}")).json()["maxSecurityLevel"] == "ask-before-acting"


async def test_members_cannot_change_the_ceiling(client: httpx.AsyncClient) -> None:
    path = await _sara_joins(client)

    response = await client.patch(path, json={"maxSecurityLevel": "autonomous"})

    assert response.status_code == 403
    await _sign_in(client, "ali@acme.dev")
    assert (await client.patch(path, json={"maxSecurityLevel": "read-only"})).status_code == 200
    await _sign_in(client, "sara@acme.dev")
    assert (await client.patch(path, json={"maxSecurityLevel": "autonomous"})).status_code == 403
    assert (await client.get(path)).json()["maxSecurityLevel"] == "read-only"


async def test_an_unknown_level_is_refused(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    response = await client.patch(f"{ORGS}/{me['organizations'][0]['id']}", json={"maxSecurityLevel": "anything"})
    assert response.status_code == 422


async def test_another_organizations_ceiling_is_out_of_reach(client: httpx.AsyncClient) -> None:
    ali = await sign_up(client, name="Ali", email="ali@acme.dev")
    alis = f"{ORGS}/{ali['organizations'][0]['id']}"
    client.cookies.clear()
    await sign_up(client, name="Sara", email="sara@acme.dev")  # an owner, of her own organization

    assert (await client.patch(alis, json={"maxSecurityLevel": "autonomous"})).status_code == 404
    assert (await client.patch(alis, json={"maxSecurityLevel": "read-only"})).status_code == 404
    await _sign_in(client, "ali@acme.dev")
    assert (await client.get(alis)).json()["maxSecurityLevel"] == "autonomous"


async def test_lowering_the_ceiling_below_the_default_lowers_the_default(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    path = f"{ORGS}/{me['organizations'][0]['id']}"

    lowered = (await client.patch(path, json={"maxSecurityLevel": "read-only"})).json()

    assert (lowered["maxSecurityLevel"], lowered["defaultSecurityLevel"]) == ("read-only", "read-only")
    # Raising the ceiling again leaves the default where it is.
    raised = (await client.patch(path, json={"maxSecurityLevel": "autonomous"})).json()
    assert (raised["maxSecurityLevel"], raised["defaultSecurityLevel"]) == ("autonomous", "read-only")


async def test_the_default_for_new_bots_stays_under_the_ceiling(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    path = f"{ORGS}/{me['organizations'][0]['id']}"
    assert (await client.patch(path, json={"maxSecurityLevel": "ask-before-acting"})).status_code == 200

    refused = await client.patch(path, json={"defaultSecurityLevel": "autonomous"})

    assert refused.status_code == 400
    assert refused.json()["detail"] == ABOVE_THE_CEILING.format(level="Ask before acting")
    # Both at once are checked together: the new ceiling, then the default under it.
    both = await client.patch(path, json={"maxSecurityLevel": "autonomous", "defaultSecurityLevel": "autonomous"})
    assert both.status_code == 200, both.text
    assert (both.json()["maxSecurityLevel"], both.json()["defaultSecurityLevel"]) == ("autonomous", "autonomous")


# Bots under it


async def test_a_member_cannot_raise_a_bot_above_the_ceiling(client: httpx.AsyncClient) -> None:
    path = await _sara_joins(client)
    await _sign_in(client, "ali@acme.dev")
    assert (await client.patch(path, json={"maxSecurityLevel": "ask-before-acting"})).status_code == 200
    await _sign_in(client, "sara@acme.dev")

    hired = await client.post(f"{path}/bots", json={"name": "Scout", "securityLevel": "autonomous"})
    assert hired.status_code == 400
    assert hired.json()["detail"] == ABOVE_THE_CEILING.format(level="Ask before acting")

    bot = (await client.post(f"{path}/bots", json={"name": "Scout"})).json()
    assert bot["securityLevel"] == "ask-before-acting"
    raised = await client.patch(f"{path}/bots/{bot['id']}", json={"securityLevel": "autonomous"})
    assert raised.status_code == 400
    assert (await client.get(f"{path}/bots/{bot['id']}")).json()["securityLevel"] == "ask-before-acting"
    # Lowering is always fine.
    lowered = await client.patch(f"{path}/bots/{bot['id']}", json={"securityLevel": "read-only"})
    assert lowered.status_code == 200 and lowered.json()["securityLevel"] == "read-only"


async def test_owners_raise_the_ceiling_before_a_bot(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    path = f"{ORGS}/{me['organizations'][0]['id']}"
    bot = (await client.post(f"{path}/bots", json={"name": "Scout"})).json()
    assert (await client.patch(path, json={"maxSecurityLevel": "ask-before-acting"})).status_code == 200

    assert (await client.patch(f"{path}/bots/{bot['id']}", json={"securityLevel": "autonomous"})).status_code == 400
    assert (await client.patch(path, json={"maxSecurityLevel": "autonomous"})).status_code == 200
    assert (await client.patch(f"{path}/bots/{bot['id']}", json={"securityLevel": "autonomous"})).status_code == 200


async def test_a_bot_already_above_a_lowered_ceiling_keeps_its_level_and_can_still_be_edited(
    client: httpx.AsyncClient,
) -> None:
    me = await sign_up(client)
    path = f"{ORGS}/{me['organizations'][0]['id']}"
    bot = (await client.post(f"{path}/bots", json={"name": "Scout", "securityLevel": "autonomous"})).json()
    assert (await client.patch(path, json={"maxSecurityLevel": "read-only"})).status_code == 200

    # The editor sends every field back, the unchanged level too: that's not raising it.
    edited = await client.patch(f"{path}/bots/{bot['id']}", json={"name": "Scout 2", "securityLevel": "autonomous"})

    assert edited.status_code == 200, edited.text
    assert (edited.json()["name"], edited.json()["securityLevel"]) == ("Scout 2", "autonomous")


async def test_lowering_the_ceiling_makes_an_existing_bot_run_at_it(providers: FakeProviders) -> None:
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        me = await sign_up(client)
        path = f"{ORGS}/{me['organizations'][0]['id']}"
        bot = (await client.post(f"{path}/bots", json={"name": "Scout", "securityLevel": "autonomous"})).json()
        thread = (await client.post(f"{path}/threads/dm", json={"botId": bot["id"]})).json()
        sent = (await client.post(f"{path}/threads/{thread['id']}/messages", json={"text": "hi"})).json()
        run_id = sent["runIds"][0]

        assert await _level(app, run_id) == "autonomous"
        assert (await client.patch(path, json={"maxSecurityLevel": "ask-before-acting"})).status_code == 200
        assert await _level(app, run_id) == "ask-before-acting"
        assert (await client.patch(path, json={"maxSecurityLevel": "read-only"})).status_code == 200
        assert await _level(app, run_id) == "read-only"
        # Raising the ceiling never loosens past the bot's own level.
        assert (await client.patch(f"{path}/bots/{bot['id']}", json={"securityLevel": "ask-before-acting"})).is_success
        assert (await client.patch(path, json={"maxSecurityLevel": "autonomous"})).status_code == 200
        assert await _level(app, run_id) == "ask-before-acting"


# Runs under it, end to end


async def _execution(world: Org, run_id: uuid.UUID, tool: str) -> ToolExecution:
    async with world.db() as db:
        query = select(ToolExecution).where(ToolExecution.run_id == run_id, ToolExecution.tool_name == tool)
        found = await db.scalar(query)
    assert found is not None, f"{tool} was never called"
    return found


async def _set_ceiling(world: Org, level: str) -> None:
    async with world.db() as db:
        await db.execute(update(Organization).where(Organization.id == world.org_id).values(max_security_level=level))
        await db.commit()


SEND = ("demo.send_email", {"to": "sara@acme.dev", "subject": "Hi"})


async def test_an_autonomous_bot_asks_under_an_ask_before_acting_ceiling(org: Org) -> None:  # noqa: F811
    assert (await org.client.patch(org.path, json={"maxSecurityLevel": "ask-before-acting"})).status_code == 200
    org.model.plans["Chief"] = [("", [SEND])]

    run_id = await org.send(await org.dm("chief"), "Email Sara")

    send = await _execution(org, run_id, "demo.send_email")
    assert (send.decision, send.status) == ("ask", "waiting_approval")
    assert (await org.run(run_id)).status == "waiting_approval"


async def test_lowering_the_ceiling_mid_run_applies_from_the_next_tool_call(org: Org) -> None:  # noqa: F811
    """The run loaded its context at Autonomous; the ceiling drops before its first tool call."""
    model = org.model

    async def model_for(_org_id: uuid.UUID, _model_id: str, *_: Any) -> Any:
        await _set_ceiling(org, "read-only")  # an admin, just after the run started
        return model

    org.runs.model_for = model_for
    org.model.plans["Chief"] = [("", [SEND])]

    run_id = await org.send(await org.dm("chief"), "Email Sara")

    send = await _execution(org, run_id, "demo.send_email")
    assert (send.decision, send.status) == ("deny", "denied")
    assert "Read only" in (send.decision_trace or "")
    # The bot is Autonomous: the refusal says it's the organization's level, not the bot's.
    assert (send.error or "").startswith("Not allowed: your organization's highest security level (Read only)")


async def test_a_handoffs_child_is_capped_by_the_ceiling(org: Org) -> None:  # noqa: F811
    assert (await org.client.patch(org.path, json={"maxSecurityLevel": "ask-before-acting"})).status_code == 200
    org.model.plans["Chief"] = [("", [handoff("sales", "Send it")])]
    org.model.plans["Sales"] = [("", [SEND])]

    parent = await org.send(await org.dm("chief"), "Go")

    (task,) = await org.tasks(parent)
    assert task.child_run_id is not None
    assert await _level(org.app, task.child_run_id) == "ask-before-acting"
    send = await _execution(org, task.child_run_id, "demo.send_email")
    assert send.decision == "ask"


async def test_a_routines_run_is_capped_by_the_ceiling(team: Team) -> None:  # noqa: F811
    await team.sign_in("ali@acme.dev")
    path = f"{ORGS}/{team.org_id}"
    assert (await team.client.patch(f"{path}/bots/{team.bot}", json={"securityLevel": "autonomous"})).is_success
    routine = await team.create(securityLevel="autonomous")
    assert (await team.client.patch(path, json={"maxSecurityLevel": "read-only"})).status_code == 200

    run_id = (await team.client.post(f"{team.url}/{routine['id']}/run-now")).json()["runId"]

    assert await _level(team.app, run_id) == "read-only"


async def test_a_new_email_triggers_a_run_capped_by_the_ceiling() -> None:
    async with acme() as world:
        bot = f"{world.org}/bots/{world.bot_id}"
        assert (await world.client.patch(bot, json={"securityLevel": "autonomous"})).is_success
        assert (await world.client.patch(world.org, json={"maxSecurityLevel": "ask-before-acting"})).status_code == 200
        await _on_and_baselined(world)
        world.google.gmail = {f"{ME}/history": history("18f1a1"), f"{ME}/messages/18f1a1": INVOICE}

        await _poll(world)

        (run,) = await _runs(world)
        assert await _level(world.app, run.id) == "ask-before-acting"


async def _approve_after(world: Org, ceiling: str) -> tuple[uuid.UUID, ToolExecution]:
    """Chief (Ask before acting) asks to send an email; the ceiling becomes `ceiling` while the
    approval waits; then someone approves it."""
    await world.client.patch(f"{world.path}/bots/{world.bots['chief']}", json={"securityLevel": "ask-before-acting"})
    world.model.plans["Chief"] = [("", [SEND])]
    run_id = await world.send(await world.dm("chief"), "Email Sara")
    assert (await world.run(run_id)).status == "waiting_approval"
    (approval,) = (await world.client.get(f"{world.path}/approvals")).json()

    assert (await world.client.patch(world.path, json={"maxSecurityLevel": ceiling})).status_code == 200
    url = f"{world.path}/approvals/{approval['id']}/decide"
    assert (await world.client.post(url, json={"decision": "approve"})).status_code == 200
    await world.runs.wait_until_idle()
    return run_id, await _execution(world, run_id, "demo.send_email")


async def test_an_approved_call_is_refused_when_the_ceiling_dropped_while_it_waited(org: Org) -> None:  # noqa: F811
    run_id, send = await _approve_after(org, "read-only")

    assert (send.status, send.started_at) == ("denied", None)  # the email was never sent
    assert send.error is not None
    assert send.error.startswith("Not done: your organization's highest security level was lowered to Read only")
    assert "deny" in send.decision_trace.rsplit("·", 1)[-1]
    assert (await org.run(run_id)).status == "succeeded"
    # The person's decision stays theirs; the tool line and the bot say why it wasn't done.
    (approval,) = (await org.client.get(f"{org.path}/approvals?status=all")).json()
    assert approval["status"] == "approved"
    finished = [data for kind, data, _ in await org.events(run_id) if kind == "tool_finished"]
    assert [(e["status"], e["error"]) for e in finished] == [("denied", send.error)]
    reply = (await org.messages(f"{org.path}/threads/{(await org.run(run_id)).thread_id}"))[-1]
    assert [(p["type"], p.get("status")) for p in reply["parts"][:2]] == [("approval", None), ("tool-call", "denied")]
    assert send.error in org.prompt_text("Chief")


async def test_an_approved_call_still_runs_when_the_lowered_ceiling_still_allows_it(org: Org) -> None:  # noqa: F811
    _, send = await _approve_after(org, "ask-before-acting")

    assert send.status == "succeeded"
