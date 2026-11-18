from pydantic import Field

from src.models.bot import AvatarColor, SecurityLevel
from src.schemas.common import ApiModel


class TemplateOut(ApiModel):
    """A ready-made bot in the marketplace. Hiring one creates a bot with these fields."""

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(max_length=80)
    category: str
    description: str = Field(max_length=2000)
    instructions: str = Field(max_length=20000)
    avatar_color: AvatarColor
    # How careful the job needs it to be. A hired bot starts at this or the organization's default
    # level, whichever is stricter.
    security_level: SecurityLevel
    # Plugin ids (like "gmail"): the apps it works in. Listed: only the ones this server loaded.
    plugins: list[str]
