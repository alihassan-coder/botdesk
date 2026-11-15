from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from src.api.deps import AppSettings, ClientIp, CurrentUser, Db, Emails, Limiter, session_token
from src.controllers import auth_controller
from src.schemas.auth import (
    AuthOptionsOut,
    ChangePasswordIn,
    ForgotPasswordIn,
    MeOut,
    MessageOut,
    ProfileUpdate,
    ResetPasswordIn,
    SignInIn,
    SignUpIn,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/options")
async def options(settings: AppSettings) -> AuthOptionsOut:
    """Public: whether sign-up is open, invite-only or closed (SIGNUP_MODE), so the web can adapt."""
    return auth_controller.options(settings)


@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
async def sign_up(
    body: SignUpIn, response: Response, db: Db, settings: AppSettings, limiter: Limiter, ip: ClientIp
) -> MeOut:
    """Create an account and sign in. With an invite token you join that organization; without one
    you get your own. SIGNUP_MODE decides whether either is allowed (403 if not)."""
    return await auth_controller.sign_up(db, settings, response, body, limiter=limiter, ip=ip)


@router.post("/sign-in")
async def sign_in(
    body: SignInIn, response: Response, db: Db, settings: AppSettings, limiter: Limiter, ip: ClientIp
) -> MeOut:
    """429 after too many attempts from one address or for one email."""
    return await auth_controller.sign_in(db, settings, response, body, limiter=limiter, ip=ip)


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(request: Request, response: Response, db: Db, settings: AppSettings) -> None:
    await auth_controller.sign_out(db, settings, response, session_token(request))


@router.get("/me")
async def me(user: CurrentUser, db: Db) -> MeOut:
    """Who is signed in. 401 if nobody is."""
    return await auth_controller.me(db, user)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    body: ForgotPasswordIn,
    db: Db,
    settings: AppSettings,
    emails: Emails,
    background: BackgroundTasks,
    limiter: Limiter,
    ip: ClientIp,
) -> MessageOut:
    """Emails a reset link if the account exists. Always the same answer, so it doesn't reveal accounts."""
    return await auth_controller.forgot_password(db, settings, emails, background, body, limiter=limiter, ip=ip)


@router.post("/reset-password")
async def reset_password(body: ResetPasswordIn, db: Db, limiter: Limiter, ip: ClientIp) -> MessageOut:
    """Set a new password from a reset link (works once, until it expires). Signs out every device."""
    return await auth_controller.reset_password(db, body, limiter=limiter, ip=ip)


@router.patch("/me")
async def update_profile(body: ProfileUpdate, user: CurrentUser, db: Db) -> MeOut:
    """Change your name or @handle (handles are unique)."""
    return await auth_controller.update_profile(db, user, body)


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, request: Request, user: CurrentUser, db: Db) -> MessageOut:
    """Needs your current password. Keeps you signed in here; signs out your other devices."""
    return await auth_controller.change_password(db, user, body, session_token(request))
