from fastapi import APIRouter
from sqlalchemy import text

from src.api.deps import Db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: Db) -> dict[str, str]:
    """For uptime checks and deploys: the API is up and can reach the database."""
    await db.execute(text("select 1"))
    return {"status": "ok"}
