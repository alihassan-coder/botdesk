from fastapi import APIRouter, status

from src.api.deps import CurrentUser, Db, OrgAccess, Runs
from src.controllers import template_controller
from src.schemas.bot import BotOut
from src.schemas.template import TemplateOut

router = APIRouter(tags=["templates"])


@router.get("/templates")
async def list_templates(_user: CurrentUser, runs: Runs) -> list[TemplateOut]:
    """The marketplace: ready-made bots, the same for every organization on this server. `plugins`
    lists only the plugins this server loaded."""
    return template_controller.list_templates(runs.registry)


@router.post("/orgs/{org_id}/templates/{template_id}/hire", status_code=status.HTTP_201_CREATED)
async def hire(template_id: str, access: OrgAccess, db: Db, runs: Runs) -> BotOut:
    """Hire a template: a bot with its name, job and instructions, at its security level or the
    organization's default, whichever is stricter, with its plugins switched on in its Tools (one
    that signs in with OAuth waits for an account) and the instance's default model. Then open its
    DM with `POST /threads/dm`. 404 for a template that isn't in the catalogue."""
    return await template_controller.hire(db, access, template_id, runs.registry)
