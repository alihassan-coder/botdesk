"""All database tables. Importing this package registers every model with `Base.metadata`
(Alembic relies on that to see the tables)."""

from src.models.bot import Bot
from src.models.invitation import Invitation
from src.models.organization import Membership, Organization
from src.models.thread import Message, Thread, ThreadParticipant
from src.models.user import Session, User

__all__ = [
    "Bot",
    "Invitation",
    "Membership",
    "Message",
    "Organization",
    "Session",
    "Thread",
    "ThreadParticipant",
    "User",
]
