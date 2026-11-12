"""Approvals: seeing them, and deciding them exactly once (ADR 0004 §3).

Who may see and decide: members of the organization who are in the approval's chat, the same
people who can see the run (a DM stays private to its member). Deciding is one conditional
UPDATE on `status = 'pending'`; whoever doesn't win gets 409. Callers own the transaction.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Select, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import as_utc, utcnow
from src.core.errors import BadRequest, Conflict, NotFound
from src.models import Approval, ThreadParticipant, ToolExecution, User
from src.models.approval import ApprovalStatus
from src.plugins.registry import ToolRegistry
from src.schemas.approval import ApprovalOut, Decider, PreviewLine
from src.services.tool_execution_service import args_hash

LIST_LIMIT = 100
ALREADY_DECIDED = "This approval was already decided."
EXPIRED = "This approval expired, so the bot didn't do it."
NOT_FOUND = "This approval doesn't exist."


@dataclass(frozen=True)
class ApprovalView:
    approval: Approval
    decider: Decider | None


def _visible_to(org_id: uuid.UUID, user_id: uuid.UUID) -> Select[Approval, uuid.UUID, str]:
    """Approvals in this organization, in chats this person is in, with who decided them (one query)."""
    in_chat = exists().where(
        ThreadParticipant.thread_id == Approval.thread_id,
        ThreadParticipant.participant_type == "user",
        ThreadParticipant.participant_id == user_id,
    )
    return (
        select(Approval, User.id, User.name)
        .outerjoin(User, User.id == Approval.decided_by)
        .where(Approval.org_id == org_id, in_chat)
    )


def _view(row: Any) -> ApprovalView:
    approval, decider_id, decider_name = row
    decider = Decider(id=decider_id, name=decider_name) if decider_id else None
    return ApprovalView(approval=approval, decider=decider)


async def list_approvals(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    status: ApprovalStatus | None = "pending",
    bot_id: uuid.UUID | None = None,
    thread_id: uuid.UUID | None = None,
    limit: int = LIST_LIMIT,
) -> list[ApprovalView]:
    """Newest first. `status=None` lists every status."""
    query = _visible_to(org_id, user_id)
    if status:
        query = query.where(Approval.status == status)
    if bot_id:
        query = query.where(Approval.bot_id == bot_id)
    if thread_id:
        query = query.where(Approval.thread_id == thread_id)
    rows = await db.execute(query.order_by(Approval.created_at.desc()).limit(limit))
    return [_view(row) for row in rows]


async def get_approval(
    db: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID, approval_id: uuid.UUID
) -> ApprovalView:
    row = (await db.execute(_visible_to(org_id, user_id).where(Approval.id == approval_id))).first()
    if row is None:
        raise NotFound(NOT_FOUND)
    return _view(row)


async def view_by_id(db: AsyncSession, approval_id: uuid.UUID) -> ApprovalView:
    """For the run itself (no person asking): the approval and who decided it."""
    query = (
        select(Approval, User.id, User.name)
        .outerjoin(User, User.id == Approval.decided_by)
        .where(Approval.id == approval_id)
        .execution_options(populate_existing=True)  # just updated: read the new values
    )
    return _view((await db.execute(query)).one())


@dataclass(frozen=True)
class Decided:
    view: ApprovalView
    expired: bool  # it had run out of time: the run is told "no", and the caller answers 409


def _checked_args(registry: ToolRegistry, tool_name: str, edited: dict[str, Any]) -> dict[str, Any]:
    tool = registry.get(tool_name)
    if tool is None:
        raise Conflict("This tool isn't available any more.")
    try:
        return tool.spec.args_model.model_validate(edited).model_dump(mode="json")
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'args'}: {e['msg']}" for e in error.errors())
        raise BadRequest(f"Those changes don't fit this action: {problems}") from error


async def decide(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user: User,
    approval_id: uuid.UUID,
    approve: bool,
    edited_args: dict[str, Any] | None,
    registry: ToolRegistry,
) -> Decided:
    """Approve (maybe with edited arguments) or deny. Only a pending approval can be decided,
    and only once, even when two people click at the same moment."""
    approval = (await get_approval(db, org_id=org_id, user_id=user.id, approval_id=approval_id)).approval
    if approval.status != "pending":
        raise Conflict(ALREADY_DECIDED)

    if as_utc(approval.expires_at) <= utcnow():
        if not await _settle(db, approval, status="expired", user_id=None, final_args=None):
            raise Conflict(ALREADY_DECIDED)
        return Decided(view=await view_by_id(db, approval.id), expired=True)

    final_args = approval.args
    if approve and edited_args is not None:
        final_args = _checked_args(registry, approval.tool_name, edited_args)
    status: ApprovalStatus = "denied"
    if approve:
        status = "edited" if final_args != approval.args else "approved"
    if not await _settle(db, approval, status=status, user_id=user.id, final_args=final_args if approve else None):
        raise Conflict(ALREADY_DECIDED)
    return Decided(view=await view_by_id(db, approval.id), expired=False)


async def _settle(
    db: AsyncSession,
    approval: Approval,
    *,
    status: ApprovalStatus,
    user_id: uuid.UUID | None,
    final_args: dict[str, Any] | None,
) -> bool:
    """The atomic part: pending → `status`, and the tool call becomes ready to run (with the
    approved arguments) or denied. False if someone else decided first."""
    won = await db.execute(
        update(Approval)
        .where(Approval.id == approval.id, Approval.status == "pending")
        .values(status=status, decided_by=user_id, decided_at=utcnow(), final_args=final_args)
        .returning(Approval.id)
    )
    if won.first() is None:
        return False
    await _settle_tool_call(db, approval.tool_execution_id, final_args)
    return True


async def _settle_tool_call(db: AsyncSession, execution_id: uuid.UUID, approved_args: dict[str, Any] | None) -> None:
    waiting = (ToolExecution.id == execution_id, ToolExecution.status == "waiting_approval")
    if approved_args is None:
        await db.execute(
            update(ToolExecution).where(*waiting).values(status="denied", error="Not approved.", finished_at=utcnow())
        )
        return
    await db.execute(
        update(ToolExecution)
        .where(*waiting)
        .values(status="ready", args=approved_args, args_hash=args_hash(approved_args))
    )


async def expire_for_run(db: AsyncSession, run_id: uuid.UUID) -> list[uuid.UUID]:
    """A run that stops (Stop pressed) can't use its pending approvals any more."""
    pending = list(await db.scalars(select(Approval).where(Approval.run_id == run_id, Approval.status == "pending")))
    return [
        approval.id
        for approval in pending
        if await _settle(db, approval, status="expired", user_id=None, final_args=None)
    ]


def _preview(args: dict[str, Any]) -> list[PreviewLine]:
    return [
        PreviewLine(label=key.replace("_", " ").capitalize(), value=value if isinstance(value, str) else str(value))
        for key, value in args.items()
    ]


def approval_out(view: ApprovalView, registry: ToolRegistry) -> ApprovalOut:
    approval = view.approval
    tool = registry.get(approval.tool_name)
    return ApprovalOut(
        id=approval.id,
        run_id=approval.run_id,
        thread_id=approval.thread_id,
        bot_id=approval.bot_id,
        tool_execution_id=approval.tool_execution_id,
        tool=approval.tool_name,
        title=approval.title,
        summary=approval.summary,
        risk_class=approval.risk,
        reason=approval.reason,
        tainted=approval.tainted,
        args=approval.args,
        final_args=approval.final_args,
        args_schema=tool.args_schema() if tool else None,
        preview=_preview(approval.final_args or approval.args),
        status=approval.status,
        requested_at=approval.created_at,
        expires_at=approval.expires_at,
        decided_at=approval.decided_at,
        decided_by=view.decider,
    )


def approval_json(view: ApprovalView, registry: ToolRegistry) -> dict[str, Any]:
    """The approval as it goes into a run event."""
    return approval_out(view, registry).model_dump(mode="json", by_alias=True)
