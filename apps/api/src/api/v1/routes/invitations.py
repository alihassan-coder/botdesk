import uuid

from fastapi import APIRouter, BackgroundTasks, status

from src.api.deps import AppSettings, CurrentUser, Db, Emails, OrgAccess
from src.controllers import invitation_controller
from src.schemas.invitation import AcceptInvitationIn, CreatedInvitationOut, InvitationIn, InvitationOut
from src.schemas.organization import OrgOut

router = APIRouter(tags=["invitations"])


@router.post("/orgs/{org_id}/invitations", status_code=status.HTTP_201_CREATED)
async def invite(
    body: InvitationIn, access: OrgAccess, db: Db, settings: AppSettings, emails: Emails, background: BackgroundTasks
) -> CreatedInvitationOut:
    """Invite an email address. Emails them the link, and returns it once so you can share it too."""
    return await invitation_controller.create(db, settings, emails, background, access, body)


@router.get("/orgs/{org_id}/invitations")
async def list_invitations(access: OrgAccess, db: Db) -> list[InvitationOut]:
    """Invites not yet accepted (and not expired). Owners and admins only."""
    return await invitation_controller.list_pending(db, access)


@router.delete("/orgs/{org_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(invitation_id: uuid.UUID, access: OrgAccess, db: Db) -> None:
    await invitation_controller.revoke(db, access, invitation_id)


@router.post("/invitations/accept")
async def accept_invitation(body: AcceptInvitationIn, user: CurrentUser, db: Db) -> OrgOut:
    """Join the organization from an invite link. Sign in with the invited email first."""
    return await invitation_controller.accept(db, user, body.token)
