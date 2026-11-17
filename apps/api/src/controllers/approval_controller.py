"""Handles approval requests: list them, look at one, decide one.

Deciding saves the decision, its event and the job that resumes the paused run in one
transaction, so a run never continues on a decision that wasn't saved, and a saved decision
always gets its run moving again.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.errors import Conflict
from src.models import Run
from src.models.approval import ApprovalStatus
from src.plugins.registry import ToolRegistry
from src.runtime.runner import RunManager
from src.schemas.approval import ApprovalOut, DecisionIn
from src.services import approval_service, mcp_server_service, run_event_service


async def _registry(db: AsyncSession, access: Access, runs: RunManager) -> ToolRegistry:
    """The loaded plugins plus this organization's MCP servers, so their cards get a schema and edits."""
    return await mcp_server_service.org_registry(db, runs.registry, access.org.id, runs.mcp)


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
    registry = await _registry(db, access, runs)
    return [approval_service.approval_out(view, registry) for view in views]


async def get_approval(db: AsyncSession, access: Access, runs: RunManager, approval_id: uuid.UUID) -> ApprovalOut:
    view = await approval_service.get_approval(
        db, org_id=access.org.id, user_id=access.user.id, approval_id=approval_id
    )
    return approval_service.approval_out(view, await _registry(db, access, runs))


async def decide(
    db: AsyncSession, access: Access, runs: RunManager, approval_id: uuid.UUID, body: DecisionIn
) -> ApprovalOut:
    approve = body.decision == "approve"
    registry = await _registry(db, access, runs)
    decided = await approval_service.decide(
        db,
        org_id=access.org.id,
        user=access.user,
        approval_id=approval_id,
        approve=approve,
        edited_args=body.edited_args,
        registry=registry,
    )
    approval = decided.view.approval
    run_event_service.add_event(
        db,
        org_id=approval.org_id,
        thread_id=approval.thread_id,
        run_id=approval.run_id,
        kind="approval_decided",
        data={"approval": approval_service.approval_json(decided.view, registry)},
    )
    run = await db.get(Run, approval.run_id)
    if run is not None:  # it carries on with the decision (expired counts as no)
        await runs.resume(db, run)
    await db.commit()
    runs.bus.announce(approval.thread_id)

    if decided.expired:
        raise Conflict(approval_service.EXPIRED)
    return approval_service.approval_out(decided.view, registry)
