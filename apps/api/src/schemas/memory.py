from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from src.schemas.common import ApiModel

# "bot": learned in group chats, so every member's chats with the bot may use it.
# "you": learned in your DM with the bot, and used only there.
MemoryScopeName = Literal["bot", "you"]


class MemoryOut(ApiModel):
    id: str
    text: str
    created_at: datetime | None
    updated_at: datetime | None
    scope: MemoryScopeName


class MemoryUpdate(ApiModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("Write what the bot should remember.")
        return text.strip()


class MemoryStatusOut(ApiModel):
    enabled: bool
    reason: str | None = None
