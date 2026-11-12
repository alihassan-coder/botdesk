import uuid

from pydantic import Field

from src.models.organization import Plan, Role
from src.schemas.common import ApiModel


class OrgOut(ApiModel):
    """An organization, with the signed-in user's role in it."""

    id: uuid.UUID
    name: str
    slug: str
    plan: Plan
    role: Role


class OrgUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")


class MemberRoleUpdate(ApiModel):
    role: Role


class MemberOut(ApiModel):
    id: uuid.UUID
    name: str
    email: str
    handle: str
    role: Role
