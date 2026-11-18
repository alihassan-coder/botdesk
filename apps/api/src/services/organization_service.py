"""Organizations and who belongs to them."""

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import BadRequest, Conflict, Forbidden, NotFound
from src.core.handles import handle_prefix, make_handle, slugify
from src.models import Membership, Organization, User
from src.models.bot import SecurityLevel
from src.runtime.policy import LEVEL_NAMES, looser_than, strictest_level
from src.schemas.organization import MemberOut, OrgOut
from src.services import provider_service

SLUG_TAKEN = "That address is taken. Try another."
SLUG_ROOM = 56  # a slug made from a name: short enough for "-NN" within the column's 64


def above_the_ceiling(ceiling: SecurityLevel) -> str:
    return (
        f"This organization's highest security level is {LEVEL_NAMES[ceiling]}. "
        "Owners and admins can raise it in Settings → Security."
    )


def require_under_ceiling(org: Organization, level: SecurityLevel, *, ceiling: SecurityLevel | None = None) -> None:
    """No bot, and no default for new bots, above the organization's ceiling (ADR 0004).
    `ceiling`: the one being saved with it, when it changes in the same request."""
    ceiling = ceiling or cast("SecurityLevel", org.max_security_level)
    if looser_than(level, ceiling):
        raise BadRequest(above_the_ceiling(ceiling))


def org_out(org: Organization, role: str) -> OrgOut:
    return OrgOut.model_validate(
        {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "role": role,
            "monthly_budget_usd": org.monthly_budget_usd,
            "default_security_level": org.default_security_level,
            "max_security_level": org.max_security_level,
        }
    )


async def create_personal_org(db: AsyncSession, owner: User) -> Organization:
    """Everyone starts with their own organization, which they own."""
    return await create_org(db, owner, name=f"{owner.name.split()[0]}'s team")


async def create_org(db: AsyncSession, owner: User, *, name: str, slug: str | None = None) -> Organization:
    """A new organization, owned by whoever creates it. Without a chosen address, one is made
    from the name (with -2, -3… when taken); a chosen address must be free."""
    name = name.strip()
    if not name:
        raise BadRequest("Give the organization a name.")
    if slug:
        if await db.scalar(select(Organization.id).where(Organization.slug == slug)):
            raise Conflict(SLUG_TAKEN)
    else:
        base = slugify(name)[:SLUG_ROOM].strip("-")
        taken = set(await db.scalars(select(Organization.slug).where(Organization.slug.like(handle_prefix(base)))))
        slug = make_handle(base, taken)
    org = Organization(name=name, slug=slug)
    try:
        async with db.begin_nested():  # two people taking the same address at once: one gets a 409
            db.add(org)
            await db.flush()
    except IntegrityError as error:
        raise Conflict(SLUG_TAKEN) from error
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


async def lock_membership(db: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Whether they're still a member, holding their membership row until the transaction ends
    (Postgres), so removing them waits for what this transaction saves for them, and takes it too."""
    query = select(Membership.user_id).where(Membership.org_id == org_id, Membership.user_id == user_id)
    return await db.scalar(query.with_for_update()) is not None


async def org_and_role(db: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID) -> tuple[Organization, str] | None:
    """The organization and the user's role in it, in one query. None if they aren't a member."""
    row = (
        await db.execute(
            select(Organization, Membership.role)
            .join(Membership, Membership.org_id == Organization.id)
            .where(Organization.id == org_id, Membership.user_id == user_id)
        )
    ).first()
    if row is None:
        return None
    org, role = row
    return org, role


async def update_org(
    db: AsyncSession,
    org: Organization,
    *,
    name: str | None,
    slug: str | None,
    default_security_level: SecurityLevel | None,
    max_security_level: SecurityLevel | None = None,
) -> Organization:
    """Checks everything before changing anything. A default for new bots must sit at or under
    the ceiling (the new one, when both change); lowering the ceiling below the default lowers the
    default with it. A lowered ceiling reaches every run at its next tool call."""
    if default_security_level:
        require_under_ceiling(org, default_security_level, ceiling=max_security_level)
    if slug and slug != org.slug:
        if await db.scalar(select(Organization.id).where(Organization.slug == slug)):
            raise Conflict(SLUG_TAKEN)
        org.slug = slug
    if name and name.strip():
        org.name = name.strip()
    if max_security_level:
        org.max_security_level = max_security_level
        current = cast("SecurityLevel", org.default_security_level)
        org.default_security_level = strictest_level(current, max_security_level)
    if default_security_level:
        org.default_security_level = default_security_level
    return org


def set_budget(org: Organization, monthly_budget_usd: int | None) -> None:
    """What all the organization's bots may spend a month. None or 0 removes the limit."""
    org.monthly_budget_usd = monthly_budget_usd or None


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
) -> list[tuple[str, uuid.UUID]]:
    """Admins remove people; anyone can leave. Owners can only be removed by owners. Their own
    model keys here go with them; returns those keys' (provider id, key id)."""
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
    return await provider_service.delete_member_keys(db, org_id, user_id)


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
