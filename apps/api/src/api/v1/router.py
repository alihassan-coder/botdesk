"""Version 1 of the API. Every route lives under /api/v1."""

from fastapi import APIRouter

from src.api.v1.routes import (
    approvals,
    auth,
    bots,
    browser,
    computer,
    connections,
    connectors,
    files,
    health,
    invitations,
    mcp_servers,
    memories,
    oauth,
    organizations,
    plugins,
    providers,
    routines,
    runs,
    templates,
    threads,
    usage,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(invitations.router)
api_router.include_router(bots.router)
api_router.include_router(browser.router)
api_router.include_router(browser.provider_router)
api_router.include_router(computer.router)
api_router.include_router(computer.provider_router)
api_router.include_router(threads.router)
api_router.include_router(runs.router)
api_router.include_router(approvals.router)
api_router.include_router(providers.router)
api_router.include_router(plugins.router)
api_router.include_router(connections.router)
api_router.include_router(connectors.router)
api_router.include_router(files.router)
api_router.include_router(oauth.router)
api_router.include_router(routines.router)
api_router.include_router(memories.router)
api_router.include_router(usage.router)
api_router.include_router(mcp_servers.router)
api_router.include_router(templates.router)
