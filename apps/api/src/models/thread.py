import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin, utcnow

ThreadKind = Literal["dm", "group"]
ParticipantType = Literal["user", "bot"]
AuthorType = Literal["user", "bot", "system"]
MessageStatus = Literal["streaming", "complete", "error"]


class Thread(IdMixin, CreatedAtMixin, Base):
    """A conversation. A DM is you and one bot (private to you); a group has people and bots."""

    __tablename__ = "threads"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(120))
    # DMs: the bot this chat is with. Removing the bot removes its DMs.
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_message_at: Mapped[datetime] = mapped_column(default=utcnow)


class ThreadParticipant(Base):
    """Who is in a thread: people and bots. Only people in a thread can see it."""

    __tablename__ = "thread_participants"

    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True)
    participant_type: Mapped[str] = mapped_column(String(10), primary_key=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, index=True)


class Message(IdMixin, CreatedAtMixin, Base):
    """One message. Its content is a list of parts (text now; cards like approvals later)."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_thread_id_created_at", "thread_id", "created_at"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"))
    author_type: Mapped[str] = mapped_column(String(10))
    author_id: Mapped[uuid.UUID | None]
    parts: Mapped[list[dict[str, Any]]]
    status: Mapped[str] = mapped_column(String(12), default="complete")

    @property
    def text(self) -> str:
        """The message's text parts, joined."""
        return "\n".join(str(part.get("text", "")) for part in self.parts if part.get("type") == "text")
