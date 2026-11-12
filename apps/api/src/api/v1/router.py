"""Version 1 of the API. Every route lives under /api/v1."""

from fastapi import APIRouter

from src.api.v1.routes import auth, health, invitations, organizations

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(invitations.router)
