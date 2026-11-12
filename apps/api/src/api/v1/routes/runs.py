import uuid

from fastapi import APIRouter

from src.api.deps import Db, OrgAccess, Runs
from src.controllers import run_controller
from src.schemas.run import RunOut

router = APIRouter(prefix="/orgs/{org_id}/runs", tags=["runs"])


@router.get("/{run_id}")
async def get_run(run_id: uuid.UUID, access: OrgAccess, db: Db) -> RunOut:
    """One run: its status, limits and error, if any."""
    return await run_controller.get_run(db, access, run_id)


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> RunOut:
    """Stop button. A queued run is cancelled at once; a running one stops within moments."""
    return await run_controller.cancel_run(db, access, runs, run_id)
