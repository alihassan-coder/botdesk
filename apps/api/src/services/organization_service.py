"""Organizations and who belongs to them."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import Conflict, Forbidden, NotFound
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


async def _owner_count(db: AsyncSession, org_id: uuid.UUID) -> int:
    owners = await db.scalars(select(Membership.user_id).where(Membership.org_id == org_id, Membership.role == "owner"))
    return len(list(owners))


async def _membership_or_404(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    membership = await get_membership(db, org_id=org_id, user_id=user_id)
    if membership is None:
        raise NotFound("That person isn't in this organization.")
    return membership


async def change_role(
    db: AsyncSession, *, org_id: uuid.UUID, actor_role: str, user_id: uuid.UUID, role: str
) -> Membership:
    """Admins manage admins and members. Only owners can make or unmake owners.
    There is always at least one owner."""
    membership = await _membership_or_404(db, org_id, user_id)
    touches_owner = "owner" in (role, membership.role)
    if touches_owner and actor_role != "owner":
        raise Forbidden("Only owners can change who is an owner.")
    if membership.role == "owner" and role != "owner" and await _owner_count(db, org_id) == 1:
        raise Conflict("An organization needs at least one owner. Make someone else owner first.")
    membership.role = role
    return membership


async def remove_member(
    db: AsyncSession, *, org_id: uuid.UUID, actor_id: uuid.UUID, actor_role: str, user_id: uuid.UUID
) -> None:
    """Admins remove people; anyone can leave. Owners can only be removed by owners."""
    membership = await _membership_or_404(db, org_id, user_id)
    leaving = actor_id == user_id
    if not leaving and actor_role not in ("owner", "admin"):
        raise Forbidden("Only owners and admins can do that.")
    if membership.role == "owner":
        if not leaving and actor_role != "owner":
            raise Forbidden("Only owners can remove an owner.")
        if await _owner_count(db, org_id) == 1:
            raise Conflict("An organization needs at least one owner. Make someone else owner first.")
    await db.delete(membership)


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
