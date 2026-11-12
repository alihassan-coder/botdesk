"""Inviting people into an organization, and accepting invites."""

import uuid
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import security
from src.core.database import as_utc, utcnow
from src.core.errors import Conflict, Forbidden, NotFound
from src.models import Invitation, Membership, Organization, User

INVALID_INVITE = "This invite link isn't valid any more. Ask for a new one."


async def invite(
    db: AsyncSession, *, org_id: uuid.UUID, email: str, role: str, invited_by: uuid.UUID, days: int
) -> tuple[Invitation, str]:
    """Create an invite and return it with its token. Re-inviting replaces the old link."""
    email = email.lower()
    already_member = await db.scalar(
        select(Membership.user_id)
        .join(User, User.id == Membership.user_id)
        .where(Membership.org_id == org_id, User.email == email)
    )
    if already_member:
        raise Conflict(f"{email} is already in this organization.")

    await db.execute(
        delete(Invitation).where(
            Invitation.org_id == org_id, Invitation.email == email, Invitation.accepted_at.is_(None)
        )
    )
    token = security.new_session_token()
    invitation = Invitation(
        org_id=org_id,
        email=email,
        role=role,
        token_hash=security.hash_token(token),
        invited_by=invited_by,
        expires_at=utcnow() + timedelta(days=days),
        accepted_at=None,
    )
    db.add(invitation)
    await db.flush()
    return invitation, token


async def pending(db: AsyncSession, org_id: uuid.UUID) -> list[Invitation]:
    rows = await db.scalars(
        select(Invitation)
        .where(Invitation.org_id == org_id, Invitation.accepted_at.is_(None), Invitation.expires_at > utcnow())
        .order_by(Invitation.created_at.desc())
    )
    return list(rows)


async def revoke(db: AsyncSession, *, org_id: uuid.UUID, invitation_id: uuid.UUID) -> None:
    invitation = await db.get(Invitation, invitation_id)
    if invitation is None or invitation.org_id != org_id or invitation.accepted_at is not None:
        raise NotFound("Invite not found.")
    await db.delete(invitation)


async def accept(db: AsyncSession, *, token: str, user: User) -> tuple[Organization, str]:
    """Join the organization. The invite must be for the signed-in user's email."""
    invitation = await db.scalar(select(Invitation).where(Invitation.token_hash == security.hash_token(token)))
    if invitation is None or invitation.accepted_at is not None or as_utc(invitation.expires_at) <= utcnow():
        raise NotFound(INVALID_INVITE)
    if invitation.email != user.email:
        raise Forbidden(f"This invite is for {invitation.email}. Sign in with that email to accept it.")

    org = await db.get(Organization, invitation.org_id)
    if org is None:
        raise NotFound(INVALID_INVITE)

    membership = await db.get(Membership, (org.id, user.id))
    if membership is None:
        membership = Membership(org_id=org.id, user_id=user.id, role=invitation.role)
        db.add(membership)
    invitation.accepted_at = utcnow()
    return org, membership.role
