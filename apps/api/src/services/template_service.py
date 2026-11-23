"""Marketplace templates (`src/templates/`): listing them, and hiring one into an organization.

Hiring is creating a bot from the template, decided here rather than by the browser: its name,
role, description, instructions and colour; the stricter of the template's security level and the
organization's default (a template never starts a bot looser than the org would); a budget a
member may give (`HIRED_BUDGET_USD`); the instance's default model; and, on top of every new
bot's default Tools, the template's plugins that this server loaded, switched on. A plugin that
signs in with OAuth (Gmail) is on with no account yet: its Tools tab asks for one.
"""

import uuid
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFound
from src.models import Bot, Organization
from src.models.bot import SecurityLevel
from src.plugins.core import CORE_PLUGIN_IDS
from src.plugins.registry import ToolRegistry
from src.runtime.policy import strictest_level
from src.schemas.bot import BotIn
from src.schemas.template import TemplateOut
from src.services import binding_service, bot_service
from src.templates import TEMPLATES

NOT_IN_MARKETPLACE = "That bot isn't in the marketplace any more."
# What a hired bot may spend a month: under the default, so any member may hire one.
HIRED_BUDGET_USD = 20


def listed(registry: ToolRegistry) -> list[TemplateOut]:
    """Every template, with only the plugins this server loaded (core ones aren't apps)."""
    loaded = {plugin.id for plugin in registry.plugins()} - CORE_PLUGIN_IDS
    return [t.model_copy(update={"plugins": [p for p in t.plugins if p in loaded]}) for t in TEMPLATES]


def find(template_id: str) -> TemplateOut:
    template = next((t for t in TEMPLATES if t.id == template_id), None)
    if template is None:
        raise NotFound(NOT_IN_MARKETPLACE)
    return template


async def hire(
    db: AsyncSession, *, org: Organization, created_by: uuid.UUID, template: TemplateOut, registry: ToolRegistry
) -> Bot:
    """The bot, with its Tools. The caller commits."""
    data = BotIn(
        name=template.name,
        role=template.role,
        description=template.description,
        instructions=template.instructions,
        avatar_color=template.avatar_color,
        model_id="",
        security_level=strictest_level(template.security_level, cast(SecurityLevel, org.default_security_level)),
        monthly_budget_usd=HIRED_BUDGET_USD,
    )
    plugins = registry.plugins()
    bot = await bot_service.create_bot(db, org=org, created_by=created_by, data=data, plugins=plugins)
    # Every new bot has the default ones already; the template's others (OAuth) are switched on too.
    extra = [p for p in plugins if p.id in template.plugins and not binding_service.on_by_default(p)]
    binding_service.switch_on(db, bot, extra)
    await db.flush()
    return bot
