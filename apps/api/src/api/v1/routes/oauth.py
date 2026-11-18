from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from src.api.deps import AppSettings, Db, OAuthFlows, Runs, session_token
from src.controllers import connection_controller, mcp_server_controller

router = APIRouter(prefix="/oauth", tags=["connections"])


@router.get("/callback", include_in_schema=False)
async def oauth_callback(
    request: Request,
    db: Db,
    oauth: OAuthFlows,
    settings: AppSettings,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
    iss: str | None = None,
) -> RedirectResponse:
    """Where a provider sends the browser back after signing in ({API_PUBLIC_URL}/api/v1/oauth/callback).
    Not org-scoped: it reads the session cookie (SameSite=Lax, so it comes along on this redirect).
    Always 303 to the web's `/apps/callback` with `result=connected` or `result=error&code=…`."""
    url = await connection_controller.finish_oauth(
        db,
        session_token(request),
        state=state,
        code=code,
        error=error,
        iss=iss,
        oauth=oauth,
        web_app_url=settings.web_app_url,
    )
    # The address this was loaded from holds the code: never pass it on as a Referer, never cache.
    headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER, headers=headers)


@router.get("/client-metadata/{file_name}", include_in_schema=False)
async def client_metadata(file_name: str, db: Db, runs: Runs) -> JSONResponse:
    """BotDesk's Client ID Metadata Document for one MCP server's sign-in (slice 7.3, ADR 0012 §3):
    `{API_PUBLIC_URL}/api/v1/oauth/client-metadata/<server id>.json` is the client id, and the
    authorization server fetches this instead of registering BotDesk. Public; nothing in it is
    secret. 404 for a server that doesn't sign in this way."""
    document = await mcp_server_controller.client_metadata(db, file_name, runs.mcp)
    return JSONResponse(document, headers={"Cache-Control": "public, max-age=300"})
