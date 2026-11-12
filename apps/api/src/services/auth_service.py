"""Accounts and sessions: sign up, sign in, sign out, who a token belongs to, and password resets."""

import uuid
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import security
from src.core.database import as_utc, utcnow
from src.core.errors import BadRequest, Conflict, Unauthorized
from src.core.handles import make_handle
from src.models import PasswordResetToken, Session, User
from src.services import organization_service

WRONG_CREDENTIALS = "That email and password don't match."
EMAIL_TAKEN = "An account with this email already exists. Sign in instead."
RESET_LINK_INVALID = "This reset link has expired or was already used. Ask for a new one."


async def sign_up(db: AsyncSession, *, name: str, email: str, password: str) -> User:
    """Create the account and a first organization that the new user owns."""
    email = email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise Conflict(EMAIL_TAKEN)

    taken_handles = set(await db.scalars(select(User.handle)))
    user = User(
        name=name,
        email=email,
        handle=make_handle(name, taken_handles),
        password_hash=security.hash_password(password),
    )
    db.add(user)
    await db.flush()
    await organization_service.create_personal_org(db, user)
    return user


async def sign_in(db: AsyncSession, *, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        security.burn_password_check(password)
        raise Unauthorized(WRONG_CREDENTIALS)
    if not security.verify_password(user.password_hash, password):
        raise Unauthorized(WRONG_CREDENTIALS)
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    return user


async def start_session(db: AsyncSession, user: User, *, days: int) -> str:
    """Create a session; return its token (the database keeps only the hash)."""
    token = security.new_session_token()
    db.add(Session(token_hash=security.hash_token(token), user_id=user.id, expires_at=utcnow() + timedelta(days=days)))
    return token


async def user_for_token(db: AsyncSession, token: str) -> User | None:
    # One query on every signed-in request: the session and its user together.
    row = (
        await db.execute(
            select(User, Session.expires_at)
            .join(Session, Session.user_id == User.id)
            .where(Session.token_hash == security.hash_token(token))
        )
    ).first()
    if row is None:
        return None
    user, expires_at = row
    return user if as_utc(expires_at) > utcnow() else None


async def end_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(Session).where(Session.token_hash == security.hash_token(token)))


async def update_profile(db: AsyncSession, user: User, *, name: str | None, handle: str | None) -> User:
    if handle and handle != user.handle:
        if await db.scalar(select(User.id).where(User.handle == handle)):
            raise Conflict(f"@{handle} is taken. Try another.")
        user.handle = handle
    if name and name.strip():
        user.name = name.strip()
    return user


async def change_password(
    db: AsyncSession, user: User, *, current_password: str, new_password: str, keep_token: str | None
) -> None:
    """Check the current password, set the new one, and sign out every other device."""
    if not security.verify_password(user.password_hash, current_password):
        # 400, not 401: the web app reads 401 as "your session ended" and signs you out.
        raise BadRequest("Your current password isn't right.")
    user.password_hash = security.hash_password(new_password)
    other_sessions = delete(Session).where(Session.user_id == user.id)
    if keep_token:
        other_sessions = other_sessions.where(Session.token_hash != security.hash_token(keep_token))
    await db.execute(other_sessions)


async def request_password_reset(db: AsyncSession, *, email: str, minutes: int) -> tuple[User, str] | None:
    """Create a reset token for this email's account; return the user and token, or None if there's no account.

    Older unused links stop working (only the newest counts). Known and unknown emails run the same
    queries, so the timing doesn't reveal who has an account; the email itself is sent afterwards.
    """
    user = await db.scalar(select(User).where(User.email == email.lower()))
    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == (user.id if user else uuid.uuid4()),
            PasswordResetToken.used_at.is_(None),
        )
    )
    if user is None:
        return None
    token = security.new_session_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=security.hash_token(token),
            expires_at=utcnow() + timedelta(minutes=minutes),
            used_at=None,
        )
    )
    return user, token


async def reset_password(db: AsyncSession, *, token: str, password: str) -> None:
    """Use a reset link once: set the new password and sign the account out everywhere."""
    now = utcnow()
    # One guarded UPDATE claims the link, so two requests can't both use it.
    user_id = await db.scalar(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == security.hash_token(token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(PasswordResetToken.user_id)
    )
    user = await db.get(User, user_id) if user_id else None
    if user is None:
        raise BadRequest(RESET_LINK_INVALID)
    user.password_hash = security.hash_password(password)
    await db.execute(delete(Session).where(Session.user_id == user.id))
