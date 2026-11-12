"""Accounts and sessions: sign up, sign in, sign out, and finding who a token belongs to."""

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import security
from src.core.database import as_utc, utcnow
from src.core.errors import Conflict, Unauthorized
from src.core.handles import make_handle
from src.models import Session, User
from src.services import organization_service

WRONG_CREDENTIALS = "That email and password don't match."
EMAIL_TAKEN = "An account with this email already exists. Sign in instead."


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
    session = await db.scalar(select(Session).where(Session.token_hash == security.hash_token(token)))
    if session is None or as_utc(session.expires_at) <= utcnow():
        return None
    return await db.get(User, session.user_id)


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
        raise Unauthorized("Your current password isn't right.")
    user.password_hash = security.hash_password(new_password)
    other_sessions = delete(Session).where(Session.user_id == user.id)
    if keep_token:
        other_sessions = other_sessions.where(Session.token_hash != security.hash_token(keep_token))
    await db.execute(other_sessions)
