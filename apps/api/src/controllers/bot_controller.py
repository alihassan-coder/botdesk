"""Handles bot requests. Any member can hire and edit bots; removing one, or changing its monthly
budget, takes an admin (members may hire a bot with a budget up to the default). Nobody sets a bot
above the organization's security level ceiling. A bot's model must belong to a connected provider
(Settings → Models & keys: the organization's key, the server's env, or the editor's own key)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.config import Settings
from src.core.errors import Forbidden
from src.models import BotTool
from src.plugins.registry import ToolRegistry
from src.runtime.runner import RunManager
from src.schemas.bot import BotIn, BotOut, BotUpdate
from src.schemas.bot_tool import BotToolsIn, BotToolsOut, BotTriggerIn
from src.services import (
    binding_service,
    bot_service,
    file_service,
    mcp_server_service,
    provider_service,
    task_service,
    trigger_service,
)
from src.services.connection_service import Actor
from src.services.credential_vault import CredentialVault
from src.services.mcp_server_service import McpRuntime


async def list_bots(db: AsyncSession, access: Access) -> list[BotOut]:
    return [BotOut.model_validate(bot) for bot in await bot_service.list_bots(db, access.org.id)]


async def get_bot(db: AsyncSession, access: Access, bot_id: uuid.UUID) -> BotOut:
    return BotOut.model_validate(await bot_service.get_bot(db, access.org.id, bot_id))


BUDGET_ADMINS_ONLY = "Only owners and admins can change budgets."
DEFAULT_BOT_BUDGET_USD: int = BotIn.model_fields["monthly_budget_usd"].default


def _is_admin(access: Access) -> bool:
    return access.role in ("owner", "admin")


async def create_bot(
    db: AsyncSession, access: Access, body: BotIn, settings: Settings, registry: ToolRegistry
) -> BotOut:
    # Budgets are money. A member hiring a bot may pick a budget up to the default (templates
    # come with smaller ones), but not a bigger one, and not 0 (no limit).
    if not _is_admin(access) and not 0 < body.monthly_budget_usd <= DEFAULT_BOT_BUDGET_USD:
        raise Forbidden(BUDGET_ADMINS_ONLY)
    await provider_service.require_usable_model(db, access.org.id, body.model_id, settings, member_id=access.user.id)
    bot = await bot_service.create_bot(
        db, org=access.org, created_by=access.user.id, data=body, plugins=registry.plugins()
    )
    await db.commit()
    return BotOut.model_validate(bot)


async def update_bot(
    db: AsyncSession, access: Access, bot_id: uuid.UUID, body: BotUpdate, settings: Settings, runs: RunManager
) -> BotOut:
    """Switching a bot from its cloud computer back to its browser stops the computer (after the
    commit, best effort); deleting it is a separate action (its disk holds the bot's work)."""
    bot = await bot_service.get_bot(db, access.org.id, bot_id)
    was_cloud = bot.computer == "cloud"
    budget = body.monthly_budget_usd
    if budget is not None and budget != bot.monthly_budget_usd and not _is_admin(access):
        raise Forbidden(BUDGET_ADMINS_ONLY)
    if body.model_id and body.model_id != bot.model_id:  # a model picked earlier stays valid
        await provider_service.require_usable_model(
            db, access.org.id, body.model_id, settings, member_id=access.user.id
        )
    await bot_service.update_bot(db, access.org, bot, body)
    await db.commit()
    if was_cloud and bot.computer != "cloud":
        await runs.computers.stop_soon(access.org.id, bot.id)
    return BotOut.model_validate(bot)


async def delete_bot(
    db: AsyncSession,
    access: Access,
    runs: RunManager,
    bot_id: uuid.UUID,
    *,
    settings: Settings,
    vault: CredentialVault,
) -> None:
    """Nothing may wait for, or keep working for, a bot that's gone: its handoffs end first (a task
    handed to it fails and its parent carries on; one handed by it is cancelled), each parent in a
    short transaction of its own. Then the runs that go with it (its own, and all in its DMs) and
    the children of those tasks are stopped, and only then is it deleted. Its files' bytes are
    removed from the organization's storage last, best effort (their rows go with the bot), and
    its cloud computer is deleted at Orgo (best effort)."""
    access.require_admin()
    await bot_service.get_bot(db, access.org.id, bot_id)  # 404 for another organization's bot
    aftermath = task_service.Aftermath()
    for parent_id in await task_service.parents_with_open_tasks_of(db, bot_id):
        ended = await task_service.bot_removed(db, bot_id, parent_id)
        for parent in ended.resume:
            await runs.resume(db, parent)
        await db.commit()
        aftermath += ended
    going = await bot_service.runs_going_with(db, bot_id)
    await db.commit()  # end the read before stopping: each stop has its own transaction
    for parent in aftermath.resume:
        runs.bus.announce(parent.thread_id)
    for run_id in dict.fromkeys([*aftermath.stop, *going]):
        await runs.stop(run_id)  # announces each run's chat (a task's child works in its parent's)
    files = await file_service.list_files(db, access.org.id, bot_id)
    # Its cloud computer's running time is recorded with it; the computer goes after the commit.
    computer_gone = await runs.computers.leaving(db, access.org.id, bot_id)
    await bot_service.delete_bot(db, await bot_service.get_bot(db, access.org.id, bot_id))
    await db.commit()
    await file_service.remove_bytes(db, files, access.org.id, settings=settings, vault=vault)
    await computer_gone()


# Tools (bindings, slice 5.2). Any member may switch a bot's plugins on and off, like editing it;
# choosing an account follows who may use it (binding_service).


async def get_tools(
    db: AsyncSession, access: Access, bot_id: uuid.UUID, registry: ToolRegistry, mcp: McpRuntime | None = None
) -> BotToolsOut:
    bot = await bot_service.get_bot(db, access.org.id, bot_id)
    registry = await mcp_server_service.org_registry(db, registry, access.org.id, mcp)  # + the org's MCP servers
    return await _tools_out(
        db, registry, await binding_service.bindings_of(db, bot.id), access.org.id, mcp, bot.computer
    )


async def _tools_out(
    db: AsyncSession,
    registry: ToolRegistry,
    bindings: dict[str, BotTool],
    org_id: uuid.UUID,
    mcp: McpRuntime | None,
    computer: str,
) -> BotToolsOut:
    subscriptions = await trigger_service.subscriptions_of(db, [binding.id for binding in bindings.values()])
    servers = await mcp_server_service.tools_tab(db, org_id) if mcp is not None else {}
    return binding_service.tools_out(registry, bindings, subscriptions, servers, computer)


async def set_tools(
    db: AsyncSession,
    access: Access,
    bot_id: uuid.UUID,
    body: BotToolsIn,
    registry: ToolRegistry,
    mcp: McpRuntime | None = None,
) -> BotToolsOut:
    bot = await bot_service.get_bot(db, access.org.id, bot_id)
    registry = await mcp_server_service.org_registry(db, registry, access.org.id, mcp)
    actor = Actor(org_id=access.org.id, user_id=access.user.id, role=access.role)
    servers = await mcp_server_service.tools_tab(db, access.org.id) if mcp is not None else {}
    bindings = await binding_service.update_bindings(
        db,
        actor,
        bot,
        registry,
        body.plugins,
        known=servers.keys(),
        check_switch=mcp_server_service.bind_check(servers),
    )
    await db.commit()
    return await _tools_out(db, registry, bindings, access.org.id, mcp, bot.computer)


async def set_trigger(
    db: AsyncSession,
    access: Access,
    bot_id: uuid.UUID,
    plugin_id: str,
    trigger: str,
    body: BotTriggerIn,
    registry: ToolRegistry,
    mcp: McpRuntime | None = None,
) -> BotToolsOut:
    """Switch a bot's trigger on (you become its subscriber) or off (slice 6.3)."""
    bot = await bot_service.get_bot(db, access.org.id, bot_id)
    registry = await mcp_server_service.org_registry(db, registry, access.org.id, mcp)
    actor = Actor(org_id=access.org.id, user_id=access.user.id, role=access.role)
    await trigger_service.set_trigger(db, actor, bot, registry, plugin_id, trigger, enabled=body.enabled)
    await db.commit()
    return await _tools_out(
        db, registry, await binding_service.bindings_of(db, bot.id), access.org.id, mcp, bot.computer
    )
