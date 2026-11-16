"""All database tables. Importing this package registers every model with `Base.metadata`
(Alembic relies on that to see the tables)."""

from src.models.approval import Approval
from src.models.bot import Bot
from src.models.bot_tool import BotTool
from src.models.connection import AuditEntry, Connection
from src.models.invitation import Invitation
from src.models.organization import Membership, Organization
from src.models.provider_credential import ProviderCredential
from src.models.routine import Routine, RoutineRun
from src.models.run import Run, RunEvent, ToolExecution
from src.models.thread import Message, Thread, ThreadParticipant
from src.models.usage import UsageRecord
from src.models.user import PasswordResetToken, Session, User

__all__ = [
    "Approval",
    "AuditEntry",
    "Bot",
    "BotTool",
    "Connection",
    "Invitation",
    "Membership",
    "Message",
    "Organization",
    "PasswordResetToken",
    "ProviderCredential",
    "Routine",
    "RoutineRun",
    "Run",
    "RunEvent",
    "Session",
    "Thread",
    "ThreadParticipant",
    "ToolExecution",
    "UsageRecord",
    "User",
]
