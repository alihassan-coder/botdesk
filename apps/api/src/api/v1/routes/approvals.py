import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from src.api.deps import Db, OrgAccess, Runs
from src.controllers import approval_controller
from src.models.approval import ApprovalStatus
from src.schemas.approval import ApprovalOut, DecisionIn

router = APIRouter(prefix="/orgs/{org_id}/approvals", tags=["approvals"])


@router.get("")
async def list_approvals(
    access: OrgAccess,
    db: Db,
    runs: Runs,
    status: ApprovalStatus | Literal["all"] = "pending",
    bot_id: Annotated[uuid.UUID | None, Query(alias="botId")] = None,
    thread_id: Annotated[uuid.UUID | None, Query(alias="threadId")] = None,
) -> list[ApprovalOut]:
    """Approvals in chats you're in, newest first (at most 100). Pending ones by default;
    `status=all` for every status."""
    return await approval_controller.list_approvals(
        db, access, runs, status=None if status == "all" else status, bot_id=bot_id, thread_id=thread_id
    )


@router.get("/{approval_id}")
async def get_approval(approval_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> ApprovalOut:
    """One approval (404 unless you're in its chat)."""
    return await approval_controller.get_approval(db, access, runs, approval_id)


@router.post("/{approval_id}/decide")
async def decide(approval_id: uuid.UUID, body: DecisionIn, access: OrgAccess, db: Db, runs: Runs) -> ApprovalOut:
    """Approve (optionally with `editedArgs`) or deny. Only once: a second decision gets 409."""
    return await approval_controller.decide(db, access, runs, approval_id, body)
