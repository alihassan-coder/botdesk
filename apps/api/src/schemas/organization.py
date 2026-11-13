import uuid

from pydantic import Field

from src.models.organization import Role
from src.schemas.common import ApiModel


class OrgOut(ApiModel):
    """An organization, with the signed-in user's role in it."""

    id: uuid.UUID
    name: str
    slug: str
    role: Role
    # What all its bots together may spend in a calendar month (UTC), in whole dollars. None = no limit.
    monthly_budget_usd: int | None = None


class OrgUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    # Send null or 0 to remove the limit; leave it out to keep it as it is.
    monthly_budget_usd: int | None = Field(default=None, ge=0, le=1_000_000)


class MemberRoleUpdate(ApiModel):
    role: Role


class MemberOut(ApiModel):
    id: uuid.UUID
    name: str
    email: str
    handle: str
    role: Role
