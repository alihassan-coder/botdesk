"""Handles organization requests: read, rename, members and their roles."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.rate_limit import RateLimiter
from src.models import User
from src.runtime.runner import RunManager
from src.schemas.organization import MemberOut, MemberRoleUpdate, OrgCreate, OrgOut, OrgUpdate
from src.services import auth_limits, organization_service, run_event_service, run_service, thread_service
from src.services.model_catalog import ModelCatalog


async def list_mine(db: AsyncSession, user: User) -> list[OrgOut]:
    return await organization_service.orgs_for_user(db, user)


async def create(db: AsyncSession, user: User, body: OrgCreate, *, limiter: RateLimiter) -> OrgOut:
    auth_limits.create_org(limiter, user_id=user.id)  # 429 after a handful an hour
    org = await organization_service.create_org(db, user, name=body.name, slug=body.slug)
    await db.commit()
    return organization_service.org_out(org, "owner")


def get_one(access: Access) -> OrgOut:
    return organization_service.org_out(access.org, access.role)


async def update(db: AsyncSession, access: Access, body: OrgUpdate) -> OrgOut:
    access.require_admin()
    org = await organization_service.update_org(
        db,
        access.org,
        name=body.name,
        slug=body.slug,
        default_security_level=body.default_security_level,
        max_security_level=body.max_security_level,
    )
    if "monthly_budget_usd" in body.model_fields_set:  # null is a value here: "no limit"
        organization_service.set_budget(org, body.monthly_budget_usd)
    await db.commit()
    return organization_service.org_out(org, access.role)


async def members(db: AsyncSession, access: Access) -> list[MemberOut]:
    return await organization_service.list_members(db, access.org.id)


async def change_role(db: AsyncSession, access: Access, user_id: uuid.UUID, body: MemberRoleUpdate) -> MemberOut:
    access.require_admin()
    await organization_service.change_role(
        db, org_id=access.org.id, actor_role=access.role, user_id=user_id, role=body.role
    )
    await db.commit()
    member = next(m for m in await organization_service.list_members(db, access.org.id) if m.id == user_id)
    return member


async def remove_member(
    db: AsyncSession, access: Access, runs: RunManager, user_id: uuid.UUID, *, catalog: ModelCatalog
) -> None:
    """Their own model keys go with them (and their cached model lists). They leave the
    organization's groups too: the people still in a group hear it live (`thread_updated`), and
    a group with nobody left is deleted once its runs are stopped."""
    removed = await organization_service.remove_member(
        db, org_id=access.org.id, actor_id=access.user.id, actor_role=access.role, user_id=user_id
    )
    left = removed.groups
    for thread in left.changed:
        run_event_service.add_event(
            db,
            org_id=access.org.id,
            thread_id=thread.id,
            run_id=None,
            kind="thread_updated",
            data={"thread": thread.model_dump(mode="json", by_alias=True, exclude={"unread"})},
        )
    going = await run_service.unfinished_in_threads(db, left.emptied)
    await db.commit()
    for provider_id, key_id in removed.keys:  # their model lists, cached apart from the org's
        catalog.forget(access.org.id, provider_id, member_key=key_id)
    for thread in left.changed:
        runs.bus.announce(thread.id)
    if left.emptied:
        for run_id in going:
            await runs.stop(run_id)
        await thread_service.delete_groups(db, left.emptied)
        await db.commit()
