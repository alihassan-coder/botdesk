from fastapi import APIRouter

from src.api.deps import CurrentUser, Db, OrgAccess
from src.controllers import organization_controller
from src.schemas.organization import MemberOut, OrgOut, OrgUpdate

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.get("")
async def list_my_orgs(user: CurrentUser, db: Db) -> list[OrgOut]:
    """The organizations you belong to, with your role in each."""
    return await organization_controller.list_mine(db, user)


@router.get("/{org_id}")
async def get_org(access: OrgAccess) -> OrgOut:
    return organization_controller.get_one(access)


@router.patch("/{org_id}")
async def update_org(body: OrgUpdate, access: OrgAccess, db: Db) -> OrgOut:
    """Rename the organization or change its address. Owners and admins only."""
    return await organization_controller.update(db, access, body)


@router.get("/{org_id}/members")
async def list_members(access: OrgAccess, db: Db) -> list[MemberOut]:
    return await organization_controller.members(db, access)
