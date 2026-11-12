"""Dependencies routes ask for: the database, the signed-in user, and org access."""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.database import get_session
from src.core.errors import Forbidden, NotFound, Unauthorized
from src.models import Organization, User
from src.runtime.runner import RunManager
from src.services import auth_service, organization_service
from src.services.email_service import EmailSender

Db = Annotated[AsyncSession, Depends(get_session)]


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


AppSettings = Annotated[Settings, Depends(get_settings)]


def get_runs(request: Request) -> RunManager:
    """Starts and stops bot runs, and wakes live streams (one per API process)."""
    runs: RunManager = request.app.state.runs
    return runs


Runs = Annotated[RunManager, Depends(get_runs)]


def get_email_sender(request: Request) -> EmailSender:
    """Brevo, or the log when there's no key (built at startup; tests swap in a fake)."""
    sender: EmailSender = request.app.state.email
    return sender


Emails = Annotated[EmailSender, Depends(get_email_sender)]


def session_token(request: Request) -> str | None:
    """The session cookie (web), or `Authorization: Bearer <token>` (desktop and mobile)."""
    if token := request.cookies.get(request.app.state.settings.session_cookie_name):
        return token
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token if scheme.lower() == "bearer" and token else None


async def current_user(request: Request, db: Db) -> User:
    token = session_token(request)
    user = await auth_service.user_for_token(db, token) if token else None
    if user is None:
        raise Unauthorized("Sign in to continue.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


@dataclass(frozen=True)
class Access:
    """The organization in the URL, and the signed-in user's role in it."""

    org: Organization
    user: User
    role: str

    def require_admin(self) -> None:
        if self.role not in ("owner", "admin"):
            raise Forbidden("Only owners and admins can do that.")


async def org_access(org_id: uuid.UUID, user: CurrentUser, db: Db) -> Access:
    """Every `/orgs/{org_id}/…` route uses this, so one org's data never leaks into another.
    Non-members get 404 (not 403), so they can't even learn the org exists."""
    found = await organization_service.org_and_role(db, org_id=org_id, user_id=user.id)
    if found is None:
        raise NotFound("Organization not found.")
    org, role = found
    return Access(org=org, user=user, role=role)


OrgAccess = Annotated[Access, Depends(org_access)]
