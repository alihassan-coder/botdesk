"""Handles approval requests: list them, look at one, decide one.

Deciding commits the decision (and its event) first, then resumes the paused run, so a run
never continues on a decision that wasn't saved.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.errors import Conflict
from src.models import Run
from src.models.approval import ApprovalStatus
from src.runtime.runner import RunManager
from src.schemas.approval import ApprovalOut, DecisionIn
from src.services import approval_service, run_event_service

DENIED_MESSAGE = "A person denied this action, so it wasn't done. Don't try it again without asking."
EXPIRED_MESSAGE = "Nobody approved this action in time, so it wasn't done."


async def list_approvals(
    db: AsyncSession,
    access: Access,
    runs: RunManager,
    *,
    status: ApprovalStatus | None,
    bot_id: uuid.UUID | None,
    thread_id: uuid.UUID | None,
) -> list[ApprovalOut]:
    views = await approval_service.list_approvals(
        db, org_id=access.org.id, user_id=access.user.id, status=status, bot_id=bot_id, thread_id=thread_id
    )
    return [approval_service.approval_out(view, runs.registry) for view in views]


async def get_approval(db: AsyncSession, access: Access, runs: RunManager, approval_id: uuid.UUID) -> ApprovalOut:
    view = await approval_service.get_approval(
        db, org_id=access.org.id, user_id=access.user.id, approval_id=approval_id
    )
    return approval_service.approval_out(view, runs.registry)


async def decide(
    db: AsyncSession, access: Access, runs: RunManager, approval_id: uuid.UUID, body: DecisionIn
) -> ApprovalOut:
    approve = body.decision == "approve"
    decided = await approval_service.decide(
        db,
        org_id=access.org.id,
        user=access.user,
        approval_id=approval_id,
        approve=approve,
        edited_args=body.edited_args,
        registry=runs.registry,
    )
    approval = decided.view.approval
    run_event_service.add_event(
        db,
        org_id=approval.org_id,
        thread_id=approval.thread_id,
        run_id=approval.run_id,
        kind="approval_decided",
        data={"approval": approval_service.approval_json(decided.view, runs.registry)},
    )
    run = await db.get(Run, approval.run_id)
    await db.commit()
    runs.bus.announce(approval.thread_id)

    if run is not None:
        if decided.expired:
            runs.resume(run, {"approved": False, "message": EXPIRED_MESSAGE})
        else:
            runs.resume(run, {"approved": approve, "message": None if approve else DENIED_MESSAGE})
    if decided.expired:
        raise Conflict(approval_service.EXPIRED)
    return approval_service.approval_out(decided.view, runs.registry)
