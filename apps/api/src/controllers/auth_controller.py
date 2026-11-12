"""Handles one auth request at a time: calls the service, saves, sets or clears the cookie."""

from urllib.parse import urlencode

from fastapi import BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.emails import password_reset_email
from src.models import User
from src.schemas.auth import (
    ChangePasswordIn,
    ForgotPasswordIn,
    MeOut,
    MessageOut,
    ProfileUpdate,
    ResetPasswordIn,
    SignInIn,
    SignUpIn,
    UserOut,
)
from src.services import auth_service, email_service, organization_service
from src.services.email_service import EmailMessage, EmailSender


def _set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_days * 24 * 60 * 60,
        httponly=True,  # page scripts can't read it
        secure=settings.is_production,  # HTTPS only in production
        samesite="lax",  # not sent on cross-site POSTs
        path="/",
    )


async def me(db: AsyncSession, user: User) -> MeOut:
    return MeOut(user=UserOut.model_validate(user), organizations=await organization_service.orgs_for_user(db, user))


async def sign_up(db: AsyncSession, settings: Settings, response: Response, body: SignUpIn) -> MeOut:
    user = await auth_service.sign_up(db, name=body.name, email=body.email, password=body.password)
    token = await auth_service.start_session(db, user, days=settings.session_days)
    await db.commit()
    _set_session_cookie(response, settings, token)
    return await me(db, user)


async def sign_in(db: AsyncSession, settings: Settings, response: Response, body: SignInIn) -> MeOut:
    user = await auth_service.sign_in(db, email=body.email, password=body.password)
    token = await auth_service.start_session(db, user, days=settings.session_days)
    await db.commit()
    _set_session_cookie(response, settings, token)
    return await me(db, user)


async def sign_out(db: AsyncSession, settings: Settings, response: Response, token: str | None) -> None:
    if token:
        await auth_service.end_session(db, token)
        await db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


async def forgot_password(
    db: AsyncSession, settings: Settings, emails: EmailSender, background: BackgroundTasks, body: ForgotPasswordIn
) -> MessageOut:
    # The same answer whether or not the account exists, so this can't be used to find accounts.
    # The email goes out after the response, so its time doesn't show either.
    found = await auth_service.request_password_reset(db, email=body.email, minutes=settings.password_reset_minutes)
    await db.commit()
    if found:
        user, token = found
        url = f"{settings.web_app_url.rstrip('/')}/reset-password?{urlencode({'token': token})}"
        message = EmailMessage.build(
            password_reset_email(url=url, minutes=settings.password_reset_minutes),
            to_email=user.email,
            to_name=user.name,
            link=url,
        )
        background.add_task(email_service.send_quietly, emails, message)
    return MessageOut(message="If that email has an account, a reset link is on its way.")


async def reset_password(db: AsyncSession, body: ResetPasswordIn) -> MessageOut:
    await auth_service.reset_password(db, token=body.token, password=body.password)
    await db.commit()
    return MessageOut(message="Password changed. Sign in with your new password.")


async def update_profile(db: AsyncSession, user: User, body: ProfileUpdate) -> MeOut:
    await auth_service.update_profile(db, user, name=body.name, handle=body.handle)
    await db.commit()
    return await me(db, user)


async def change_password(db: AsyncSession, user: User, body: ChangePasswordIn, token: str | None) -> MessageOut:
    await auth_service.change_password(
        db, user, current_password=body.current_password, new_password=body.new_password, keep_token=token
    )
    await db.commit()
    return MessageOut(message="Password changed. Your other devices are signed out.")
