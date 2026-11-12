import uuid
from datetime import datetime
from typing import Literal

from pydantic import EmailStr

from src.schemas.common import ApiModel

InviteRole = Literal["admin", "member"]


class InvitationIn(ApiModel):
    email: EmailStr
    role: InviteRole = "member"


class InvitationOut(ApiModel):
    id: uuid.UUID
    email: str
    role: InviteRole
    created_at: datetime
    expires_at: datetime


class CreatedInvitationOut(InvitationOut):
    """Returned once, right after inviting: the link to share. It can't be shown again."""

    invite_url: str


class AcceptInvitationIn(ApiModel):
    token: str
