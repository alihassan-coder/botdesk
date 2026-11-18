import uuid

from pydantic import Field

from src.models.bot import SecurityLevel
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
    # What a new bot gets when whoever hires it doesn't pick a level.
    default_security_level: SecurityLevel = "ask-before-acting"
    # The ceiling: no bot in the organization acts above it. "autonomous" = no ceiling.
    max_security_level: SecurityLevel = "autonomous"


class OrgCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    # Leave it out to get one made from the name.
    slug: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")


class OrgUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    # Send null or 0 to remove the limit; leave it out to keep it as it is.
    monthly_budget_usd: int | None = Field(default=None, ge=0, le=1_000_000)
    default_security_level: SecurityLevel | None = None
    max_security_level: SecurityLevel | None = None


class MemberRoleUpdate(ApiModel):
    role: Role


class MemberOut(ApiModel):
    id: uuid.UUID
    name: str
    email: str
    handle: str
    role: Role
