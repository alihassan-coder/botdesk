from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse

from src.api.deps import AppSettings, Db, OAuthFlows, session_token
from src.controllers import connection_controller

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
