"""Approvals: seeing them, and deciding them exactly once (ADR 0004 §3).

Who may see and decide: members of the organization who are in the approval's chat, the same
people who can see the run (a DM stays private to its member). A call through a member's own
connection is decided only by that member (slice 5.2): anyone else gets 403. Deciding is one conditional
UPDATE on `status = 'pending'`; whoever doesn't win gets 409. Callers own the transaction.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Select, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import as_utc, utcnow
from src.core.errors import BadRequest, Conflict, Forbidden, NotFound
from src.models import Approval, Connection, ThreadParticipant, ToolExecution, User
from src.models.approval import ApprovalStatus
from src.plugins.registry import RegisteredTool, ToolRegistry
from src.schemas.approval import ApprovalOut, Decider, PreviewLine
from src.services.tool_execution_service import args_hash

LIST_LIMIT = 100
ALREADY_DECIDED = "This approval was already decided."
EXPIRED = "This approval expired, so the bot didn't do it."
NOT_FOUND = "This approval doesn't exist."
NOT_YOUR_ACCOUNT = "Only the member whose account this uses can decide it."
# What the paused run is told when it carries on (the model reads these).
DENIED_MESSAGE = "A person denied this action, so it wasn't done. Don't try it again without asking."
EXPIRED_MESSAGE = "Nobody approved this action in time, so it wasn't done."
EXPIRE_BATCH = 100  # approvals the expiry job handles per tick


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


def summarize(tool: RegisteredTool, args: dict[str, Any]) -> str:
    """The card's one-line summary of a call with these arguments. Used when the approval is
    asked for and again after an edit, so the summary always matches what will run."""
    return tool.spec.summary(tool.spec.args_model.model_validate(args))


def _checked_args(registry: ToolRegistry, tool_name: str, edited: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """The edited arguments, validated, and the summary they give."""
    tool = registry.get(tool_name)
    if tool is None:
        raise Conflict("This tool isn't available any more.")
    try:
        args = tool.spec.args_model.model_validate(edited).model_dump(mode="json")
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'args'}: {e['msg']}" for e in error.errors())
        raise BadRequest(f"Those changes don't fit this action: {problems}") from error
    return args, summarize(tool, args)


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
    await _require_may_decide(db, approval, user.id)
    if approval.status != "pending":
        raise Conflict(ALREADY_DECIDED)

    if as_utc(approval.expires_at) <= utcnow():
        if not await _settle(db, approval, status="expired", user_id=None, final_args=None):
            raise Conflict(ALREADY_DECIDED)
        return Decided(view=await view_by_id(db, approval.id), expired=True)

    final_args, summary = approval.args, approval.summary
    if approve and edited_args is not None:
        final_args, summary = _checked_args(registry, approval.tool_name, edited_args)
    status: ApprovalStatus = "denied"
    if approve:
        status = "edited" if final_args != approval.args else "approved"
    settled = await _settle(
        db,
        approval,
        status=status,
        user_id=user.id,
        final_args=final_args if approve else None,
        summary=summary if status == "edited" else None,
    )
    if not settled:
        raise Conflict(ALREADY_DECIDED)
    return Decided(view=await view_by_id(db, approval.id), expired=False)


async def _require_may_decide(db: AsyncSession, approval: Approval, user_id: uuid.UUID) -> None:
    """A call through a member-owned connection acts as that member: only they decide it. Calls
    through a bot's or the organization's connection keep the chat's rule (its members)."""
    if approval.connection_id is None:
        return
    owner = await db.execute(
        select(Connection.owner_kind, Connection.owner_user_id).where(Connection.id == approval.connection_id)
    )
    row = owner.first()
    if row is not None and row.owner_kind == "member" and row.owner_user_id != user_id:
        raise Forbidden(NOT_YOUR_ACCOUNT)


async def _settle(
    db: AsyncSession,
    approval: Approval,
    *,
    status: ApprovalStatus,
    user_id: uuid.UUID | None,
    final_args: dict[str, Any] | None,
    summary: str | None = None,
) -> bool:
    """The atomic part: pending → `status`, and the tool call becomes ready to run (with the
    approved arguments) or denied. An edit also replaces the summary, so the card describes
    what runs. False if someone else decided first."""
    values: dict[str, Any] = {"status": status, "decided_by": user_id, "decided_at": utcnow(), "final_args": final_args}
    if summary is not None:
        values["summary"] = summary
    won = await db.execute(
        update(Approval)
        .where(Approval.id == approval.id, Approval.status == "pending")
        .values(**values)
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


async def status_of(db: AsyncSession, approval_id: uuid.UUID) -> str | None:
    return await db.scalar(select(Approval.status).where(Approval.id == approval_id))


def resume_answer(status: str | None) -> dict[str, Any] | None:
    """What a paused run continues with, from its approval's status: `{"approved", "message"}`.
    None while nobody has decided. Expired counts as no; so does an approval that's gone."""
    if status == "pending":
        return None
    if status in ("approved", "edited"):
        return {"approved": True, "message": None}
    return {"approved": False, "message": DENIED_MESSAGE if status == "denied" else EXPIRED_MESSAGE}


async def overdue(db: AsyncSession, *, limit: int = EXPIRE_BATCH) -> list[uuid.UUID]:
    """Pending approvals past their `expires_at`, oldest first."""
    rows = await db.scalars(
        select(Approval.id)
        .where(Approval.status == "pending", Approval.expires_at <= utcnow())
        .order_by(Approval.expires_at)
        .limit(limit)
    )
    return list(rows)


async def expire(db: AsyncSession, approval_id: uuid.UUID) -> bool:
    """Nobody answered in time: pending → expired, and its tool call is denied. False if someone
    decided it first. The caller commits."""
    approval = await db.get(Approval, approval_id)
    if approval is None or approval.status != "pending":
        return False
    return await _settle(db, approval, status="expired", user_id=None, final_args=None)


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
