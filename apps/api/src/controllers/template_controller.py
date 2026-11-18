"""Handles marketplace template requests. Anyone signed in sees the catalogue; any member of an
organization may hire from it (the same rule as creating a bot)."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.plugins.registry import ToolRegistry
from src.schemas.bot import BotOut
from src.schemas.template import TemplateOut
from src.services import template_service


def list_templates(registry: ToolRegistry) -> list[TemplateOut]:
    return template_service.listed(registry)


async def hire(db: AsyncSession, access: Access, template_id: str, registry: ToolRegistry) -> BotOut:
    template = template_service.find(template_id)
    bot = await template_service.hire(
        db, org=access.org, created_by=access.user.id, template=template, registry=registry
    )
    await db.commit()
    return BotOut.model_validate(bot)
