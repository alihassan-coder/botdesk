import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.api.deps import Db, OrgAccess, Runs
from src.controllers import routine_controller
from src.schemas.routine import RoutineIn, RoutineOut, RoutineRunOut, RoutineUpdate, RunNowOut

router = APIRouter(prefix="/orgs/{org_id}/routines", tags=["routines"])


@router.get("")
async def list_routines(
    access: OrgAccess, db: Db, bot_id: Annotated[uuid.UUID | None, Query(alias="botId")] = None
) -> list[RoutineOut]:
    """The organization's routines, oldest first. `?botId=` for one bot's."""
    return await routine_controller.list_routines(db, access, bot_id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_routine(body: RoutineIn, access: OrgAccess, db: Db, runs: Runs) -> RoutineOut:
    """A bot repeats `instructions` on `cron` (5 fields) in `timezone` (IANA, the creator's).
    Each run happens in the creator's DM with the bot, acting for the creator."""
    return await routine_controller.create_routine(db, access, runs, body)


@router.patch("/{routine_id}")
async def update_routine(routine_id: uuid.UUID, body: RoutineUpdate, access: OrgAccess, db: Db) -> RoutineOut:
    """Switch it on or off, or edit it. Its creator, owners and admins."""
    return await routine_controller.update_routine(db, access, routine_id, body)


@router.delete("/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routine(routine_id: uuid.UUID, access: OrgAccess, db: Db) -> None:
    await routine_controller.delete_routine(db, access, routine_id)


@router.post("/{routine_id}/run-now", status_code=status.HTTP_202_ACCEPTED)
async def run_now(routine_id: uuid.UUID, access: OrgAccess, db: Db, runs: Runs) -> RunNowOut:
    """Run it once now, without moving its schedule. 409 while its last run is still going."""
    return await routine_controller.run_now(db, access, runs, routine_id)


@router.get("/{routine_id}/runs")
async def recent_runs(routine_id: uuid.UUID, access: OrgAccess, db: Db) -> list[RoutineRunOut]:
    """Its 20 most recent runs, newest first."""
    return await routine_controller.recent_runs(db, access, routine_id)
