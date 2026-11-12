import uuid

from fastapi import APIRouter, status

from src.api.deps import CurrentUser, Db, OrgAccess
from src.controllers import organization_controller
from src.schemas.organization import MemberOut, MemberRoleUpdate, OrgOut, OrgUpdate

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


@router.patch("/{org_id}/members/{user_id}")
async def change_member_role(user_id: uuid.UUID, body: MemberRoleUpdate, access: OrgAccess, db: Db) -> MemberOut:
    """Owners and admins change roles; only owners make or unmake owners."""
    return await organization_controller.change_role(db, access, user_id, body)


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(user_id: uuid.UUID, access: OrgAccess, db: Db) -> None:
    """Remove someone (owners and admins), or leave (your own id). The last owner can't leave."""
    await organization_controller.remove_member(db, access, user_id)
