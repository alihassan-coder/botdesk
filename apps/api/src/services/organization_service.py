"""Organizations and who belongs to them."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import Conflict
from src.core.handles import make_handle
from src.models import Membership, Organization, User
from src.schemas.organization import MemberOut, OrgOut


def org_out(org: Organization, role: str) -> OrgOut:
    return OrgOut.model_validate({"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan, "role": role})


async def create_personal_org(db: AsyncSession, owner: User) -> Organization:
    """Everyone starts with their own organization, which they own."""
    name = f"{owner.name.split()[0]}'s team"
    taken_slugs = set(await db.scalars(select(Organization.slug)))
    org = Organization(name=name, slug=make_handle(name, taken_slugs))
    db.add(org)
    await db.flush()
    db.add(Membership(org_id=org.id, user_id=owner.id, role="owner"))
    return org


async def orgs_for_user(db: AsyncSession, user: User) -> list[OrgOut]:
    rows = await db.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.created_at)
    )
    return [org_out(org, role) for org, role in rows]


async def get_membership(db: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID) -> Membership | None:
    return await db.get(Membership, (org_id, user_id))


async def update_org(db: AsyncSession, org: Organization, *, name: str | None, slug: str | None) -> Organization:
    if slug and slug != org.slug:
        if await db.scalar(select(Organization.id).where(Organization.slug == slug)):
            raise Conflict("That address is taken. Try another.")
        org.slug = slug
    if name and name.strip():
        org.name = name.strip()
    return org


async def list_members(db: AsyncSession, org_id: uuid.UUID) -> list[MemberOut]:
    rows = await db.execute(
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.org_id == org_id)
        .order_by(Membership.created_at)
    )
    return [
        MemberOut.model_validate({"id": u.id, "name": u.name, "email": u.email, "handle": u.handle, "role": role})
        for u, role in rows
    ]
