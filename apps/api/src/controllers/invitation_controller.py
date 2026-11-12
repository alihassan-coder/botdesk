"""Handles invite requests: send, list, revoke, accept."""

import uuid

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.config import Settings
from src.emails import invitation_email
from src.models import Invitation, User
from src.schemas.invitation import CreatedInvitationOut, InvitationIn, InvitationOut
from src.schemas.organization import OrgOut
from src.services import email_service, invitation_service, organization_service
from src.services.email_service import EmailMessage, EmailSender


def _out(invitation: Invitation) -> InvitationOut:
    return InvitationOut.model_validate(invitation)


async def create(
    db: AsyncSession,
    settings: Settings,
    emails: EmailSender,
    background: BackgroundTasks,
    access: Access,
    body: InvitationIn,
) -> CreatedInvitationOut:
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
    invite_url = f"{settings.web_app_url.rstrip('/')}/invite/{token}"
    # Emailed after the response. The link is also returned once, so the admin can share it by hand.
    message = EmailMessage.build(
        invitation_email(inviter_name=access.user.name, org_name=access.org.name, url=invite_url),
        to_email=invitation.email,
        link=invite_url,
    )
    background.add_task(email_service.send_quietly, emails, message)
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
