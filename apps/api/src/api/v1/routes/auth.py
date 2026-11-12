from fastapi import APIRouter, Request, Response, status

from src.api.deps import AppSettings, CurrentUser, Db, session_token
from src.controllers import auth_controller
from src.schemas.auth import (
    ChangePasswordIn,
    ForgotPasswordIn,
    MeOut,
    MessageOut,
    ProfileUpdate,
    SignInIn,
    SignUpIn,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
async def sign_up(body: SignUpIn, response: Response, db: Db, settings: AppSettings) -> MeOut:
    """Create an account (and its first organization) and sign in."""
    return await auth_controller.sign_up(db, settings, response, body)


@router.post("/sign-in")
async def sign_in(body: SignInIn, response: Response, db: Db, settings: AppSettings) -> MeOut:
    return await auth_controller.sign_in(db, settings, response, body)


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(request: Request, response: Response, db: Db, settings: AppSettings) -> None:
    await auth_controller.sign_out(db, settings, response, session_token(request))


@router.get("/me")
async def me(user: CurrentUser, db: Db) -> MeOut:
    """Who is signed in. 401 if nobody is."""
    return await auth_controller.me(db, user)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(body: ForgotPasswordIn) -> MessageOut:
    return await auth_controller.forgot_password()


@router.patch("/me")
async def update_profile(body: ProfileUpdate, user: CurrentUser, db: Db) -> MeOut:
    """Change your name or @handle (handles are unique)."""
    return await auth_controller.update_profile(db, user, body)


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, request: Request, user: CurrentUser, db: Db) -> MessageOut:
    """Needs your current password. Keeps you signed in here; signs out your other devices."""
    return await auth_controller.change_password(db, user, body, session_token(request))
