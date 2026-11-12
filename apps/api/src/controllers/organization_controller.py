"""Handles organization requests: read, rename, list members."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.models import User
from src.schemas.organization import MemberOut, OrgOut, OrgUpdate
from src.services import organization_service


async def list_mine(db: AsyncSession, user: User) -> list[OrgOut]:
    return await organization_service.orgs_for_user(db, user)


def get_one(access: Access) -> OrgOut:
    return organization_service.org_out(access.org, access.role)


async def update(db: AsyncSession, access: Access, body: OrgUpdate) -> OrgOut:
    access.require_admin()
    org = await organization_service.update_org(db, access.org, name=body.name, slug=body.slug)
    await db.commit()
    return organization_service.org_out(org, access.role)


async def members(db: AsyncSession, access: Access) -> list[MemberOut]:
    return await organization_service.list_members(db, access.org.id)
