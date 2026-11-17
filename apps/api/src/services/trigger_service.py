"""Triggers (slice 6.3, ADR 0011 §5): a bot reacting to something in another app, such as new
email in its Gmail.

Switching one on (`set_trigger`) adds a `TriggerSubscription` for the bot's binding; the member
who does it is the subscriber. Who may: whoever may choose the binding's account (ADR 0010 §3):
a member's own Gmail only that member; the organization's, owners and admins; the bot's own, also
its creator. Anyone who can change the bot's Tools may switch it off.

The every-minute `poll_triggers` job polls each subscription (`poll`), one at a time and each on
its own, so one that fails never holds up the rest:

1. `prepare` (short transaction): is it still usable? Its plugin and trigger are loaded, the
   binding is on with an active account, and the subscriber may still use that account. If not,
   `problem` says why and nothing else happens (a `needs_reconnect` account pauses it). A
   binding moved to another account starts again from "now" (no cursor).
2. `poll_plugin`: the plugin's `poll(ctx, cursor)` with no transaction open; `ctx.http` reaches the account.
3. `record` (one transaction, the row locked, the cursor still the one polled): in the
   subscriber's DM with the bot, each new event becomes a system message ("New email from Sara
   Lee: Invoice 4471") with a `trigger-event` part, and a queued run (hop 0, the subscriber its
   requester) that starts **tainted** when the trigger's events are outside text. A notice
   ("BotDesk missed some new mail…") is a system message with no run. Then the new cursor and
   the handled ids (`seen`, the newest `SEEN_KEPT`) are saved.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from botdesk_plugin_sdk import PluginManifest, ToolContext, TriggerPollResult, TriggerSpec
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.errors import BadRequest, Conflict, Forbidden, NotFound
from src.models import Bot, BotTool, Connection, Membership, Message, Run, Thread, TriggerSubscription
from src.plugins.registry import ToolRegistry
from src.runtime.tool_access import ToolAccessProvider
from src.services import binding_service, run_service, thread_service
from src.services.connection_service import Actor
from src.services.run_event_service import add_event

SEEN_KEPT = 200
POLL_TIMEOUT_SECONDS = 30.0
NO_TRIGGER = "This app has no such trigger."
TURN_ON_FIRST = "Switch {app} on for this bot and choose its account first."
RECONNECT_FIRST = "{account} needs reconnecting first (Connect apps)."


# The Tools tab


async def subscriptions_of(db: AsyncSession, binding_ids: Sequence[uuid.UUID]) -> list[TriggerSubscription]:
    if not binding_ids:
        return []
    return list(await db.scalars(select(TriggerSubscription).where(TriggerSubscription.binding_id.in_(binding_ids))))


def _plugin_with(registry: ToolRegistry, plugin_id: str, trigger: str) -> PluginManifest:
    """The loaded plugin, if it has this trigger (404 otherwise)."""
    plugin = registry.plugin(plugin_id)
    if plugin is None:
        raise NotFound(binding_service.UNKNOWN_PLUGIN)
    if not any(t.name == trigger for t in plugin.triggers):
        raise NotFound(NO_TRIGGER)
    return plugin


async def set_trigger(
    db: AsyncSession, actor: Actor, bot: Bot, registry: ToolRegistry, plugin_id: str, trigger: str, *, enabled: bool
) -> None:
    """Switch a bot's trigger on (the actor becomes its subscriber) or off. Doing what's already
    done changes nothing. The caller commits."""
    plugin = _plugin_with(registry, plugin_id, trigger)
    binding = (await binding_service.bindings_of(db, bot.id)).get(plugin_id)
    existing = (
        await db.scalar(
            select(TriggerSubscription).where(
                TriggerSubscription.binding_id == binding.id, TriggerSubscription.trigger == trigger
            )
        )
        if binding is not None
        else None
    )
    if not enabled:
        if existing is not None:
            await db.delete(existing)
        return
    if existing is not None:
        return
    if binding is None or not binding.enabled or binding.connection_id is None:
        raise Conflict(TURN_ON_FIRST.format(app=plugin.name))
    connection = await db.get(Connection, binding.connection_id)
    # The same rule as choosing the account: its runs act for the subscriber on that account.
    binding_service.check_can_bind(actor, bot, plugin_id, connection)
    assert connection is not None
    if connection.status != "active":
        raise Conflict(RECONNECT_FIRST.format(account=connection.account_label))
    db.add(
        TriggerSubscription(
            org_id=bot.org_id,
            binding_id=binding.id,
            trigger=trigger,
            subscriber_id=actor.user_id,
            connection_id=connection.id,
            seen=[],
        )
    )
    try:
        await db.flush()
    except IntegrityError as error:  # switched on twice at once
        raise Conflict("This bot's Tools changed a moment ago. Refresh and try again.") from error


# Polling


async def all_ids(db: AsyncSession) -> list[uuid.UUID]:
    """Every subscription, the longest unpolled first."""
    rows = await db.scalars(
        select(TriggerSubscription.id).order_by(
            TriggerSubscription.last_polled_at.is_not(None), TriggerSubscription.last_polled_at
        )
    )
    return list(rows)


@dataclass(frozen=True)
class Target:
    """A subscription ready to poll: what was read in step 1."""

    id: uuid.UUID
    org_id: uuid.UUID
    bot_id: uuid.UUID
    plugin_id: str
    subscriber_id: uuid.UUID
    connection_id: uuid.UUID
    cursor: str | None
    spec: TriggerSpec


async def prepare(db: AsyncSession, registry: ToolRegistry, subscription_id: uuid.UUID) -> Target | str | None:
    """Step 1. A `Target`, or why this subscription can't be polled now (saved as its problem),
    or None if it's gone. The caller commits."""
    row = (
        await db.execute(
            select(TriggerSubscription, BotTool, Connection)
            .join(BotTool, BotTool.id == TriggerSubscription.binding_id)
            .outerjoin(Connection, Connection.id == BotTool.connection_id)
            .where(TriggerSubscription.id == subscription_id)
        )
    ).first()
    if row is None:
        return None
    subscription, binding, connection = row
    problem = await _problem(db, registry, subscription, binding, connection)
    if problem is not None:
        subscription.problem = problem
        return problem
    assert connection is not None
    if subscription.connection_id != connection.id:  # another account now: start from "now" there
        subscription.connection_id, subscription.cursor, subscription.seen = connection.id, None, []
    plugin = registry.plugin(binding.plugin_id)
    assert plugin is not None
    spec = next(t for t in plugin.triggers if t.name == subscription.trigger)
    return Target(
        id=subscription.id,
        org_id=subscription.org_id,
        bot_id=binding.bot_id,
        plugin_id=binding.plugin_id,
        subscriber_id=subscription.subscriber_id,
        connection_id=connection.id,
        cursor=subscription.cursor,
        spec=spec,
    )


async def _problem(
    db: AsyncSession,
    registry: ToolRegistry,
    subscription: TriggerSubscription,
    binding: BotTool,
    connection: Connection | None,
) -> str | None:
    plugin = registry.plugin(binding.plugin_id)
    if plugin is None or not any(t.name == subscription.trigger for t in plugin.triggers):
        return "This app isn't on this server any more."
    if not binding.enabled or connection is None or connection.status == "revoked":
        return TURN_ON_FIRST.format(app=plugin.name)
    if connection.status != "active":
        return f"Paused: {RECONNECT_FIRST.format(account=connection.account_label)}"
    role = await db.scalar(
        select(Membership.role).where(
            Membership.org_id == subscription.org_id, Membership.user_id == subscription.subscriber_id
        )
    )
    if role is None:
        return "Whoever switched this on left the organization. Switch it on again."
    bot = await db.get(Bot, binding.bot_id)
    assert bot is not None  # the binding goes with its bot
    try:
        # Still the rule for switching it on: an admin made a member, or the binding moved to
        # another member's account, stops it.
        actor = Actor(org_id=subscription.org_id, user_id=subscription.subscriber_id, role=role)
        binding_service.check_can_bind(actor, bot, binding.plugin_id, connection)
    except (Forbidden, NotFound, BadRequest):
        return "Whoever switched this on may no longer use this account. Someone who may can switch it on again."
    return None


async def poll_plugin(access: ToolAccessProvider, target: Target) -> TriggerPollResult:
    """Step 2: the plugin's poll, through the account. No transaction is open."""
    async with access.open_plugin(
        target.org_id, target.plugin_id, connection_id=target.connection_id, timeout_seconds=POLL_TIMEOUT_SECONDS
    ) as opened:
        context = ToolContext(
            org_id=target.org_id,
            bot_id=target.bot_id,
            run_id=target.id,  # no run yet: the subscription stands in
            tool_call_id=f"trigger:{target.spec.name}",
            idempotency_key=f"{target.id}:{target.cursor}",
            logger=logging.getLogger(f"src.plugins.{target.plugin_id}"),
            http=opened.http,
            connection=opened.connection,
        )
        return await target.spec.poll(context, target.cursor)


async def record(
    db: AsyncSession, target: Target, result: TriggerPollResult, *, settings: Settings, now: datetime
) -> tuple[Thread | None, list[Run]]:
    """Step 3. The messages and runs for new events, and the new cursor. Nothing if the
    subscription was removed or polled by someone else meanwhile. The caller commits."""
    subscription = await db.scalar(
        select(TriggerSubscription).where(TriggerSubscription.id == target.id).with_for_update()
    )
    if (
        subscription is None
        or subscription.cursor != target.cursor
        or subscription.connection_id != target.connection_id
    ):
        return None, []
    seen = list(subscription.seen or [])
    new = [event for event in result.events if event.external_id not in seen]
    thread = None
    runs: list[Run] = []
    if new or result.notice:
        thread = await thread_service.open_dm(
            db, org_id=target.org_id, user_id=target.subscriber_id, bot_id=target.bot_id
        )
    for event in new:
        part: dict[str, Any] = {
            "type": run_service.TRIGGER_EVENT_PART,
            "pluginId": target.plugin_id,
            "trigger": target.spec.name,
            "title": target.spec.title,
            "externalId": event.external_id,
            "payload": event.payload,
        }
        assert thread is not None
        message = _system_message(db, thread, [thread_service.text_part(event.summary), part])
        await db.flush()
        run = run_service.queued_run(
            thread, bot_id=target.bot_id, trigger=message, settings=settings, requester_id=target.subscriber_id
        )
        run.tainted = target.spec.untrusted_payload  # outside text from its first step (ADR 0011 §4)
        db.add(run)
        await db.flush()
        await _saved(db, message, thread, run.id)
        runs.append(run)
        seen.append(event.external_id)
    if result.notice and thread is not None:
        notice = _system_message(db, thread, [thread_service.text_part(result.notice)])
        await _saved(db, notice, thread, None)
    subscription.cursor = result.cursor
    subscription.seen = seen[-SEEN_KEPT:]
    subscription.problem = None
    subscription.last_polled_at = now
    return thread, runs


def _system_message(db: AsyncSession, thread: Thread, parts: list[dict[str, Any]]) -> Message:
    message = Message(
        org_id=thread.org_id, thread_id=thread.id, author_type="system", author_id=None, parts=parts, status="complete"
    )
    db.add(message)
    return message


async def _saved(db: AsyncSession, message: Message, thread: Thread, run_id: uuid.UUID | None) -> None:
    await db.flush()
    thread.last_message_at = message.created_at
    out = thread_service.message_out(message).model_dump(mode="json", by_alias=True)
    add_event(db, org_id=thread.org_id, thread_id=thread.id, run_id=run_id, kind="message_saved", data={"message": out})


async def save_problem(db: AsyncSession, subscription_id: uuid.UUID, problem: str) -> None:
    subscription = await db.get(TriggerSubscription, subscription_id)
    if subscription is not None:
        subscription.problem = problem
