import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from src.models.bot import AvatarColor, SecurityLevel
from src.schemas.common import ApiModel

MODEL_ID_PATTERN = r"^([a-z0-9-]+:[A-Za-z0-9._-]+)?$"  # "provider:model" or empty


class BotIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(default="", max_length=20000)
    avatar_color: AvatarColor = "indigo"
    model_id: str = Field(default="", max_length=120, pattern=MODEL_ID_PATTERN)
    security_level: SecurityLevel = "ask-before-acting"
    monthly_budget_usd: int = Field(default=50, ge=0, le=100_000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, name: str) -> str:
        if not name.strip():
            raise ValueError("Give the bot a name.")
        return name.strip()


class BotUpdate(ApiModel):
    """Only the fields you send change."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    role: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=20000)
    avatar_color: AvatarColor | None = None
    model_id: str | None = Field(default=None, max_length=120, pattern=MODEL_ID_PATTERN)
    security_level: SecurityLevel | None = None
    monthly_budget_usd: int | None = Field(default=None, ge=0, le=100_000)


class BotOut(ApiModel):
    id: uuid.UUID
    name: str
    handle: str
    role: str
    description: str
    instructions: str
    avatar_color: AvatarColor
    model_id: str
    security_level: SecurityLevel
    monthly_budget_usd: int
    # Live status comes with bot runs; until then every bot is idle.
    status: Literal["idle", "working", "waiting-approval", "sleeping", "error"] = "idle"
    created_at: datetime
