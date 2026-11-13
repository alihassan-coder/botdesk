import uuid
from datetime import datetime
from typing import Any, Literal

from botdesk_plugin_sdk import RiskClass
from pydantic import Field

from src.models.approval import ApprovalStatus
from src.schemas.common import ApiModel


class PreviewLine(ApiModel):
    label: str
    value: str


class Decider(ApiModel):
    id: uuid.UUID
    name: str


class ApprovalOut(ApiModel):
    """A paused tool call. `args` is what the bot asked for; `finalArgs` what was approved
    (different when someone edited them). `argsSchema` is the tool's JSON Schema, for an edit form."""

    id: uuid.UUID
    run_id: uuid.UUID
    thread_id: uuid.UUID
    bot_id: uuid.UUID
    tool_execution_id: uuid.UUID
    tool: str
    title: str
    summary: str
    risk_class: RiskClass
    reason: str
    tainted: bool
    args: dict[str, Any]
    final_args: dict[str, Any] | None
    args_schema: dict[str, Any] | None
    preview: list[PreviewLine]
    status: ApprovalStatus
    requested_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    decided_by: Decider | None


class DecisionIn(ApiModel):
    decision: Literal["approve", "deny"]
    # Approve with changed arguments. Checked against the tool's schema.
    edited_args: dict[str, Any] | None = Field(default=None)
