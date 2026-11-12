"""Handles invite requests: send, list, revoke, accept."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.config import Settings
from src.models import Invitation, User
from src.schemas.invitation import CreatedInvitationOut, InvitationIn, InvitationOut
from src.schemas.organization import OrgOut
from src.services import invitation_service, organization_service


def _out(invitation: Invitation) -> InvitationOut:
    return InvitationOut.model_validate(invitation)


async def create(db: AsyncSession, settings: Settings, access: Access, body: InvitationIn) -> CreatedInvitationOut:
    access.require_admin()
    invitation, token = await invitation_service.invite(
        db,
        org_id=access.org.id,
        email=body.email,
        role=body.role,
        invited_by=access.user.id,
        days=settings.invitation_days,
    )
    await db.commit()
    # Emailing the link comes with the email provider; for now the admin copies and shares it.
    invite_url = f"{settings.web_app_url.rstrip('/')}/invite/{token}"
    return CreatedInvitationOut(**_out(invitation).model_dump(), invite_url=invite_url)


async def list_pending(db: AsyncSession, access: Access) -> list[InvitationOut]:
    access.require_admin()
    return [_out(invitation) for invitation in await invitation_service.pending(db, access.org.id)]


async def revoke(db: AsyncSession, access: Access, invitation_id: uuid.UUID) -> None:
    access.require_admin()
    await invitation_service.revoke(db, org_id=access.org.id, invitation_id=invitation_id)
    await db.commit()


async def accept(db: AsyncSession, user: User, token: str) -> OrgOut:
    org, role = await invitation_service.accept(db, token=token, user=user)
    await db.commit()
    return organization_service.org_out(org, role)
