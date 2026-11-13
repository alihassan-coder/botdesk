"""The `tool_executions` record: every tool call, before and after it runs (ADR 0004 §2).

`run_id` + `tool_call_id` is the idempotency key. Preparing a call twice finds the first row;
running it twice finds `started` or `succeeded` and doesn't call the tool again. Every change
of status is a conditional UPDATE. Callers own the transaction (they commit).
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import utcnow
from src.models import Approval, Run, ToolExecution


def args_hash(args: dict[str, Any]) -> str:
    """SHA-256 of the arguments in a canonical form, so the same call always hashes the same."""
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class RunRef:
    """The run a tool call belongs to."""

    run_id: uuid.UUID
    org_id: uuid.UUID
    thread_id: uuid.UUID
    bot_id: uuid.UUID


@dataclass(frozen=True)
class NewCall:
    """A prepared call, ready to record. `status` follows from the policy's decision."""

    tool_call_id: str
    tool_name: str
    args: dict[str, Any]
    risk: str
    decision: str  # auto | ask | deny | invalid
    trace: str
    error: str | None = None


@dataclass(frozen=True)
class ApprovalDraft:
    """What the approval card shows, for calls the policy says to ask about."""

    title: str
    summary: str
    tainted: bool
    expires_at: datetime


@dataclass(frozen=True)
class Recorded:
    execution: ToolExecution
    approval: Approval | None
    created: bool  # False when this call was already recorded (the node ran again)


_STATUS_FOR = {"auto": "ready", "ask": "waiting_approval", "deny": "denied", "invalid": "failed"}


async def find(db: AsyncSession, run_id: uuid.UUID, tool_call_id: str) -> Recorded | None:
    row = (
        await db.execute(
            select(ToolExecution, Approval)
            .outerjoin(Approval, Approval.tool_execution_id == ToolExecution.id)
            .where(ToolExecution.run_id == run_id, ToolExecution.tool_call_id == tool_call_id)
        )
    ).first()
    return Recorded(execution=row[0], approval=row[1], created=False) if row else None


async def record_call(db: AsyncSession, run: RunRef, call: NewCall, approval: ApprovalDraft | None) -> Recorded:
    """Save the call (and its approval when the policy asks), or return what's already saved."""
    if existing := await find(db, run.run_id, call.tool_call_id):
        return existing
    now = utcnow()
    execution = ToolExecution(
        id=uuid.uuid4(),
        org_id=run.org_id,
        run_id=run.run_id,
        tool_call_id=call.tool_call_id,
        tool_name=call.tool_name,
        status=_STATUS_FOR[call.decision],
        risk=call.risk,
        decision=call.decision,
        decision_trace=call.trace,
        args=call.args,
        args_hash=args_hash(call.args),
        error=call.error,
        created_at=now,
        finished_at=now if call.decision in ("deny", "invalid") else None,
    )
    pending = None
    if call.decision == "ask" and approval:
        pending = Approval(
            org_id=run.org_id,
            run_id=run.run_id,
            thread_id=run.thread_id,
            bot_id=run.bot_id,
            tool_execution_id=execution.id,
            tool_name=call.tool_name,
            risk=call.risk,
            title=approval.title,
            summary=approval.summary,
            reason=call.trace,
            tainted=approval.tainted,
            args=call.args,
            status="pending",
            created_at=now,
            expires_at=approval.expires_at,
        )
    try:
        async with db.begin_nested():
            db.add(execution)
            await db.flush()  # the approval points at this row, so it goes in first
            if pending:
                db.add(pending)
                await db.flush()
    except IntegrityError:  # recorded a moment ago by another attempt
        if existing := await find(db, run.run_id, call.tool_call_id):
            return existing
        raise
    return Recorded(execution=execution, approval=pending, created=True)


async def get(db: AsyncSession, execution_id: uuid.UUID) -> ToolExecution | None:
    return await db.get(ToolExecution, execution_id, populate_existing=True)


async def claim(db: AsyncSession, execution_id: uuid.UUID, *, from_status: str = "ready") -> bool:
    """Mark the call `started` just before the tool runs. Only one caller can win."""
    result = await db.execute(
        update(ToolExecution)
        .where(ToolExecution.id == execution_id, ToolExecution.status == from_status)
        .values(status="started", started_at=utcnow())
        .returning(ToolExecution.id)
    )
    return result.first() is not None


async def finish(
    db: AsyncSession, execution_id: uuid.UUID, *, result: dict[str, Any] | None = None, error: str | None = None
) -> None:
    """`succeeded` with its result, or `failed` with why."""
    await db.execute(
        update(ToolExecution)
        .where(ToolExecution.id == execution_id, ToolExecution.status == "started")
        .values(status="failed" if error else "succeeded", result=result, error=error, finished_at=utcnow())
    )


async def mark_run_tainted(db: AsyncSession, run_id: uuid.UUID) -> None:
    """The run has read outside text. From now on, risky calls ask (ADR 0004 §5)."""
    await db.execute(update(Run).where(Run.id == run_id).values(tainted=True))


# How a finished call shows in the reply. Calls in any other state never reach a saved reply.
_SHOWN_STATUSES = ("succeeded", "failed", "denied")


async def reply_cards(db: AsyncSession, run_id: uuid.UUID) -> list[dict[str, Any]]:
    """The cards a run's reply keeps above its text, in the order the calls were made: each
    call's approval card (if it asked), then its tool line ("Used Send email · done"), the same
    as they showed live. One query."""
    rows = await db.execute(
        select(ToolExecution, Approval.id)
        .outerjoin(Approval, Approval.tool_execution_id == ToolExecution.id)
        .where(ToolExecution.run_id == run_id)
        .order_by(ToolExecution.created_at, ToolExecution.id)
    )
    cards: list[dict[str, Any]] = []
    for execution, approval_id in rows:
        if approval_id:
            cards.append({"type": "approval", "approvalId": str(approval_id)})
        if execution.status in _SHOWN_STATUSES and not _denied_by_a_person(execution, approval_id):
            cards.append(tool_call_part(execution))
    return cards


def _denied_by_a_person(execution: ToolExecution, approval_id: uuid.UUID | None) -> bool:
    """Its approval card already says so (Denied or Expired); a tool line would repeat it."""
    return approval_id is not None and execution.status == "denied"


def tool_call_part(execution: ToolExecution) -> dict[str, Any]:
    """A `tool-call` message part. Same fields as the `tool_finished` event the web shows live."""
    part: dict[str, Any] = {
        "type": "tool-call",
        "toolExecutionId": str(execution.id),
        "tool": execution.tool_name,
        "status": execution.status,
    }
    if execution.error and execution.status != "succeeded":
        part["error"] = execution.error
    return part


async def runs_with_a_started_call(db: AsyncSession, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Of these runs, the ones with a tool call left `started` (we can't tell if it finished),
    and that tool's name."""
    if not run_ids:
        return {}
    rows = await db.execute(
        select(ToolExecution.run_id, ToolExecution.tool_name).where(
            ToolExecution.run_id.in_(run_ids), ToolExecution.status == "started"
        )
    )
    return {run_id: tool_name for run_id, tool_name in rows}
