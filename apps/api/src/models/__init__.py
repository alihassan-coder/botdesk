"""All database tables. Importing this package registers every model with `Base.metadata`
(Alembic relies on that to see the tables)."""

from src.models.approval import Approval
from src.models.bot import Bot
from src.models.bot_tool import BotTool
from src.models.computer_provider import ComputerProvider
from src.models.connection import AuditEntry, Connection
from src.models.file import File
from src.models.invitation import Invitation
from src.models.mcp_server import McpServer
from src.models.oauth_flow import OAuthFlow
from src.models.organization import Membership, Organization
from src.models.provider_credential import ProviderCredential
from src.models.routine import Routine, RoutineRun
from src.models.run import Run, RunEvent, ToolExecution
from src.models.task import Task
from src.models.thread import Message, Thread, ThreadParticipant
from src.models.trigger_subscription import TriggerSubscription
from src.models.usage import UsageRecord
from src.models.user import PasswordResetToken, Session, User

__all__ = [
    "Approval",
    "AuditEntry",
    "Bot",
    "BotTool",
    "ComputerProvider",
    "Connection",
    "File",
    "Invitation",
    "McpServer",
    "Membership",
    "Message",
    "OAuthFlow",
    "Organization",
    "PasswordResetToken",
    "ProviderCredential",
    "Routine",
    "RoutineRun",
    "Run",
    "RunEvent",
    "Session",
    "Task",
    "Thread",
    "ThreadParticipant",
    "ToolExecution",
    "TriggerSubscription",
    "UsageRecord",
    "User",
]
