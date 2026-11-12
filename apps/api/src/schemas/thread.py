import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from src.models.thread import AuthorType, MessageStatus, ParticipantType, ThreadKind
from src.schemas.common import ApiModel


class ParticipantOut(ApiModel):
    type: ParticipantType
    id: uuid.UUID


class ThreadOut(ApiModel):
    id: uuid.UUID
    kind: ThreadKind
    title: str
    bot_id: uuid.UUID | None
    participants: list[ParticipantOut]
    last_message_at: datetime
    last_message_preview: str


class OpenDmIn(ApiModel):
    bot_id: uuid.UUID


class GroupIn(ApiModel):
    title: str = Field(min_length=1, max_length=120)
    bot_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class AuthorOut(ApiModel):
    type: AuthorType
    id: uuid.UUID | None


class MessageOut(ApiModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    author: AuthorOut
    parts: list[dict[str, Any]]
    status: MessageStatus
    created_at: datetime


class MessageIn(ApiModel):
    text: str = Field(min_length=1, max_length=20_000)
