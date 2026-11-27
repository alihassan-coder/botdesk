"""Bots' cloud computers (ADR 0020): the organization's provider (Orgo, with its key) and each bot's
computer there, from first use to idle stop.

The provider is a `computer_providers` row of kind "computer" (ADR 0017's table): the key sealed
by the vault, its last 4 shown, and in `config` the Orgo workspace the bots' computers live in
("BotDesk", found or made when the key is saved) and `status` ("ok", or "key_refused" once Orgo
answers 401).

A bot's computer (`BotComputer`) is made on first use: a tool call, or Start in its Computer tab.
`Computers.ensure_running` makes it (Linux, 2 vCPU, 8 GB, `botdesk-<handle>`), starts a stopped
one, and waits until it runs. One creator at a time: whoever inserts the row makes the computer,
with the row's id as Orgo's Idempotency-Key, so a retry never makes two. No transaction is open
while Orgo is called. A computer Orgo no longer has (404) is forgotten: the next use makes a new
one, and the bot is told its old files are gone.

Every stop (idle, Stop, switching the bot back to its browser, removing the key, deleting the
computer or its bot) records the running time as usage (`kind="computer"`, ORGO_PRICE_PER_HOUR).
"""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.computers.base import (
    ComputerError,
    ComputerProvider,
    Gone,
    KeyRefused,
    MayHaveRun,
    NameTaken,
    NotRunning,
    RemoteComputer,
)
from src.computers.orgo import MODEL_ID, OrgoComputers
from src.core.config import Settings
from src.core.database import utcnow
from src.core.errors import BadRequest
from src.models import Bot, BotComputer
from src.models import ComputerProvider as ProviderRow
from src.schemas.computer import (
    ComputerAppOut,
    ComputerOut,
    ComputerPreviewOut,
    ComputerProviderIn,
    ComputerProviderOut,
)
from src.services import usage_service
from src.services.credential_vault import CredentialVault

logger = logging.getLogger(__name__)

KIND = "computer"  # computer_providers.kind
ORGO = "orgo"
WORKSPACE = "BotDesk"
ORGO_COMPUTER_URL = "https://www.orgo.ai/computers/{id}"

NO_PROVIDER = "An owner or admin can add an Orgo key in Settings → Computers."
NEEDS_PROVIDER = "Add an Orgo key in Settings → Computers first."
NEEDS_KEY = "Add your Orgo API key."
KEY_DIDNT_WORK = "That key didn't work: {why}"
REFUSED_KEY = "Orgo refused it. Copy it again from orgo.ai/api-keys."
NOT_RUNNING = "The computer isn't running. Start it first."
OLD_ONE_GONE = "Your old computer was gone at Orgo, so this is a new one: the files and apps from before aren't on it."
GONE_NOW = (
    "Your computer was gone at Orgo, with its files. Try again: a new one will be made, and anything "
    "you need on it must be set up again."
)
NOT_STARTED = "The computer didn't start within {minutes} minutes. Try again in a moment."
ANSWER_LOST = "Orgo didn't answer while making the computer. Try again: it will be found, not made twice."
BOT_GONE = "This bot isn't there any more."

START_SECONDS = 300  # longest a start (or a first make) is waited for
CREATOR_STALE = timedelta(minutes=5)  # a creator that went quiet this long is taken over
TOUCH_EVERY = timedelta(seconds=30)  # `last_used_at` is written at most this often


# The organization's provider


async def find_provider(db: AsyncSession, org_id: uuid.UUID) -> ProviderRow | None:
    return await db.scalar(select(ProviderRow).where(ProviderRow.org_id == org_id, ProviderRow.kind == KIND))


def provider_view(row: ProviderRow | None) -> ComputerProviderOut:
    if row is None:
        return ComputerProviderOut(provider=None, key_hint=None, checked_at=None, status=None)
    status = "key_refused" if row.config.get("status") == "key_refused" else "ok"
    return ComputerProviderOut(provider=ORGO, key_hint=row.secret_hint, checked_at=row.checked_at, status=status)


def provider_for(key: str, settings: Settings, transport: httpx.AsyncBaseTransport | None) -> ComputerProvider:
    return OrgoComputers(key, base_url=settings.orgo_api_url, transport=transport)


def _key_of(row: ProviderRow, vault: CredentialVault) -> str:
    key: str = json.loads(vault.unseal(row.encrypted_secret))["api_key"]
    return key


async def choose_provider(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: ComputerProviderIn,
    settings: Settings,
    vault: CredentialVault,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderRow:
    """Check the key live (`GET /api/me`), find or make the "BotDesk" workspace, and keep the key
    sealed. The caller commits. Another account or workspace than before: the bots' computers
    there are stopped (best effort, with the old key) and forgotten."""
    existing = await find_provider(db, org_id)
    if body.api_key:
        key = body.api_key.strip()
    elif existing is not None:
        key = _key_of(existing, vault)
    else:
        raise BadRequest(NEEDS_KEY)
    orgo = provider_for(key, settings, transport)
    try:
        await orgo.check()
        workspace_id = await orgo.workspace(WORKSPACE)
    except ComputerError as error:
        why = REFUSED_KEY if isinstance(error, KeyRefused) else str(error)
        raise BadRequest(KEY_DIDNT_WORK.format(why=why)) from None
    if existing is not None and existing.config.get("workspace_id") != workspace_id:
        await _leave_workspace(db, org_id, provider_for(_key_of(existing, vault), settings, transport), settings)
    row = existing or ProviderRow(org_id=org_id, kind=KIND, created_by=user_id)
    row.provider = ORGO
    row.config = {"workspace_id": workspace_id, "status": "ok"}
    row.encrypted_secret = vault.seal(json.dumps({"api_key": key}))
    row.secret_hint = key[-4:]
    row.checked_at = utcnow()
    db.add(row)
    return row


async def _leave_workspace(db: AsyncSession, org_id: uuid.UUID, old: ComputerProvider, settings: Settings) -> None:
    rows = list(await db.scalars(select(BotComputer).where(BotComputer.org_id == org_id)))
    for row in rows:
        if row.remote_id and row.status not in ("stopped", "stopping"):
            try:
                await old.stop(row.remote_id)
            except (ComputerError, MayHaveRun) as error:
                logger.warning("Computer %s at the old Orgo account wasn't stopped: %s", row.id, error)
        bill(db, row, utcnow(), settings)
    await db.execute(delete(BotComputer).where(BotComputer.org_id == org_id))


def bill(db: AsyncSession, row: BotComputer, now: datetime, settings: Settings) -> None:
    """Record the computer's running time since it started as usage, once. The caller commits."""
    if row.started_at is None:
        return
    hours = max((now - row.started_at).total_seconds(), 0.0) / 3600
    usage_service.record(
        db,
        org_id=row.org_id,
        bot_id=row.bot_id,
        run_id=None,
        provider=row.provider,
        model_id=MODEL_ID,
        input_tokens=0,
        output_tokens=0,
        cost_usd=round(hours * settings.orgo_price_per_hour, 6),
        kind="computer",
    )
    row.started_at = None


def computer_name(handle: str) -> str:
    return f"botdesk-{handle}"[:80]


# A bot's computer


@dataclass(frozen=True)
class Seen:
    """A bot's computer row as read in one short transaction (no database object is shared)."""

    id: uuid.UUID
    org_id: uuid.UUID
    bot_id: uuid.UUID
    remote_id: str
    name: str
    status: str
    created_at: datetime
    attempt: int
    error: str | None

    @classmethod
    def of(cls, row: BotComputer) -> "Seen":
        return cls(
            row.id, row.org_id, row.bot_id, row.remote_id, row.name, row.status, row.created_at, row.attempt, row.error
        )

    @property
    def idempotency_key(self) -> str:
        return f"botdesk-{self.id}-{self.attempt}"


@dataclass(frozen=True)
class Ready:
    """A running computer, to work on."""

    provider: ComputerProvider
    remote_id: str
    note: str | None = None  # for the bot, once: a new computer replaced one that was gone


@dataclass(frozen=True)
class _Account:
    provider: ComputerProvider
    workspace_id: str


class Computers:
    """One per run manager. `transport` replaces the network (tests' fake Orgo); main.py sets it to
    the app's `outbound`. `poll_seconds` is how often a starting computer is looked at again."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        vault: CredentialVault,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        poll_seconds: float = 2.0,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.settings = settings
        self.vault = vault
        self.transport = transport
        self.poll_seconds = poll_seconds
        self._background: set[asyncio.Task[None]] = set()

    # The organization's key

    async def _account(self, org_id: uuid.UUID) -> _Account:
        async with self.sessionmaker() as db:
            row = await find_provider(db, org_id)
        if row is None:
            raise ComputerError(NO_PROVIDER)
        provider = provider_for(_key_of(row, self.vault), self.settings, self.transport)
        return _Account(provider, str(row.config.get("workspace_id", "")))

    async def provider(self, org_id: uuid.UUID) -> ComputerProvider:
        return (await self._account(org_id)).provider

    @asynccontextmanager
    async def watching(self, org_id: uuid.UUID) -> AsyncIterator[None]:
        """Around any call to the provider: a refused key shows as "key refused" in Settings."""
        try:
            yield
        except KeyRefused:
            await self._key_refused(org_id)
            raise

    async def _key_refused(self, org_id: uuid.UUID) -> None:
        async with self.sessionmaker() as db:
            row = await find_provider(db, org_id)
            if row is not None and row.config.get("status") != "key_refused":
                row.config = {**row.config, "status": "key_refused"}
                await db.commit()

    # Running

    async def ensure_running(self, org_id: uuid.UUID, bot_id: uuid.UUID, *, claimed: Seen | None = None) -> Ready:
        """The bot's computer, running: made on first use, started when stopped, waited for while
        it starts. `claimed`: the row the caller just inserted (it is the creator)."""
        account = await self._account(org_id)
        provider = account.provider
        loop = asyncio.get_running_loop()
        deadline = loop.time() + START_SECONDS
        note: str | None = None
        while True:
            if claimed is not None:
                seen, mine = claimed, True
                claimed = None
            else:
                seen, mine = await self._claim_or_read(org_id, bot_id, provider.provider)
            if not seen.remote_id:
                maker = seen if mine else await self._take_over(seen)
                if maker is not None:
                    await self._make(maker, account)
                    continue
                await self._wait(deadline)  # another caller is making it
                continue
            if seen.status == "running":
                await self.touch(bot_id, force=True)
                return Ready(provider, seen.remote_id, note)
            try:
                remote = await provider.get(seen.remote_id)
                if remote.status == "gone":
                    raise Gone(GONE_NOW)
                if remote.status == "running":
                    await self._running(seen.id, remote)
                    continue
                if remote.status in ("stopped", "error"):
                    await provider.start(seen.remote_id)
                    await self._set_status(seen.id, "starting")
            except Gone:
                await self._forget(seen.id)
                note = OLD_ONE_GONE
                continue
            except ComputerError as error:
                if error.code != "busy":  # another start or stop holds it: look again shortly
                    await self._set_status(seen.id, "error", error=str(error))
                    raise
            await self._wait(deadline)

    async def _claim_or_read(self, org_id: uuid.UUID, bot_id: uuid.UUID, provider: str) -> tuple[Seen, bool]:
        """The bot's computer row, or a new one this caller now makes (True)."""
        async with self.sessionmaker() as db:
            row = await db.scalar(select(BotComputer).where(BotComputer.bot_id == bot_id))
            if row is not None:
                return Seen.of(row), False
            bot = await db.get(Bot, bot_id)
            if bot is None or bot.org_id != org_id:
                raise ComputerError(BOT_GONE)
            row = BotComputer(
                org_id=org_id,
                bot_id=bot_id,
                provider=provider,
                name=computer_name(bot.handle),
                status="creating",
                attempt=1,
            )
            db.add(row)
            try:
                await db.commit()
            except IntegrityError:  # another caller inserted it first: it makes the computer
                await db.rollback()
                row = await db.scalar(select(BotComputer).where(BotComputer.bot_id == bot_id))
                if row is None:
                    raise ComputerError("The computer couldn't be set up. Try again.") from None
                return Seen.of(row), False
            return Seen.of(row), True

    async def _take_over(self, seen: Seen) -> Seen | None:
        """Make it now, instead of a creator that failed or went quiet (one caller wins: the row's
        `created_at` changes). After a refusal (nothing was made) it's a new attempt, with a new
        idempotency key; after a lost answer, or a quiet creator, the same key, so Orgo answers
        with the computer it may already have made."""
        if seen.status != "error" and utcnow() - seen.created_at < CREATOR_STALE:
            return None
        attempt = seen.attempt + (1 if seen.status == "error" and seen.error != ANSWER_LOST else 0)
        now = utcnow()
        async with self.sessionmaker() as db:
            taken = await db.execute(
                update(BotComputer)
                .where(
                    BotComputer.id == seen.id,
                    BotComputer.remote_id == "",
                    BotComputer.status == seen.status,
                    BotComputer.created_at == seen.created_at,
                )
                .values(created_at=now, status="creating", error=None, attempt=attempt)
            )
            await db.commit()
        if getattr(taken, "rowcount", 0) != 1:
            return None
        return replace(seen, created_at=now, status="creating", error=None, attempt=attempt)

    async def _make(self, seen: Seen, account: _Account) -> None:
        """Make the computer at Orgo. A refusal stays on the row for people to see (the next try
        is a new attempt); a lost answer too (the next try finds what was made)."""
        try:
            try:
                remote = await account.provider.create(
                    workspace_id=account.workspace_id, name=seen.name, idempotency_key=seen.idempotency_key
                )
            except NameTaken:
                # A computer of that name is there already (one BotDesk lost track of): another name.
                remote = await account.provider.create(
                    workspace_id=account.workspace_id,
                    name=f"{seen.name[:74]}-{seen.id.hex[:4]}",
                    idempotency_key=f"{seen.idempotency_key}-b",
                )
        except MayHaveRun:
            await self._set_status(seen.id, "error", error=ANSWER_LOST)
            raise ComputerError(ANSWER_LOST) from None
        except ComputerError as error:
            await self._set_status(seen.id, "error", error=str(error))
            raise
        async with self.sessionmaker() as db:
            row = await db.get(BotComputer, seen.id)
            if row is None:  # its bot was removed meanwhile: don't leave the computer running
                await _quietly(account.provider.delete(remote.id))
                raise ComputerError(BOT_GONE)
            row.remote_id = remote.id
            row.name = remote.name or row.name
            _copy_size(row, remote)
            row.status = "starting"
            await db.commit()

    async def _running(self, row_id: uuid.UUID, remote: RemoteComputer) -> None:
        async with self.sessionmaker() as db:
            row = await db.get(BotComputer, row_id)
            if row is None:
                raise ComputerError(BOT_GONE)
            now = utcnow()
            row.status = "running"
            row.started_at = row.started_at or now
            row.last_used_at = now
            row.error = None
            _copy_size(row, remote)
            await db.commit()

    async def _set_status(self, row_id: uuid.UUID, status: str, *, error: str | None = None) -> None:
        async with self.sessionmaker() as db:
            await db.execute(update(BotComputer).where(BotComputer.id == row_id).values(status=status, error=error))
            await db.commit()

    async def _forget(self, row_id: uuid.UUID) -> None:
        """Orgo has no such computer (or none was made): the next use makes a new one."""
        async with self.sessionmaker() as db:
            row = await db.get(BotComputer, row_id)
            if row is not None:
                bill(db, row, utcnow(), self.settings)
                await db.delete(row)
            await db.commit()

    async def _wait(self, deadline: float) -> None:
        if asyncio.get_running_loop().time() > deadline:
            raise ComputerError(NOT_STARTED.format(minutes=START_SECONDS // 60))
        await asyncio.sleep(self.poll_seconds)

    async def forget_gone(self, bot_id: uuid.UUID) -> None:
        """A call answered 404: forget the bot's computer (it's gone at Orgo)."""
        async with self.sessionmaker() as db:
            row_id = await db.scalar(select(BotComputer.id).where(BotComputer.bot_id == bot_id))
        if row_id is not None:
            await self._forget(row_id)

    async def mark_stopped(self, bot_id: uuid.UUID) -> None:
        """Orgo says it isn't running (stopped outside BotDesk): bill it and say so."""
        async with self.sessionmaker() as db:
            row = await db.scalar(select(BotComputer).where(BotComputer.bot_id == bot_id))
            if row is not None and row.status == "running":
                bill(db, row, utcnow(), self.settings)
                row.status = "stopped"
            await db.commit()

    async def touch(self, bot_id: uuid.UUID, *, force: bool = False) -> None:
        """A tool call, a take-over or someone watching: the idle stop counts from now. Written at
        most every 30 seconds (watching asks for a screen every second)."""
        now = utcnow()
        query = update(BotComputer).where(BotComputer.bot_id == bot_id)
        if not force:
            query = query.where(or_(BotComputer.last_used_at.is_(None), BotComputer.last_used_at < now - TOUCH_EVERY))
        async with self.sessionmaker() as db:
            await db.execute(query.values(last_used_at=now))
            await db.commit()

    # For people (the Computer tab)

    async def start_soon(self, org_id: uuid.UUID, bot_id: uuid.UUID) -> None:
        """Start (or first make) the bot's computer in the background: the tab shows it creating or
        starting at once, then running."""
        account = await self._account(org_id)
        seen, mine = await self._claim_or_read(org_id, bot_id, account.provider.provider)
        if seen.status == "running":
            return
        if seen.remote_id and seen.status in ("stopped", "error"):
            await self._set_status(seen.id, "starting")
        self._spawn(self._start_quietly(org_id, bot_id, seen if mine else None))

    async def _start_quietly(self, org_id: uuid.UUID, bot_id: uuid.UUID, claimed: Seen | None) -> None:
        try:
            async with self.watching(org_id):
                await self.ensure_running(org_id, bot_id, claimed=claimed)
        except (ComputerError, MayHaveRun) as error:  # it's on the row, for the tab to show
            logger.info("Bot %s's computer didn't start: %s", bot_id, error)
        except Exception:
            logger.exception("Bot %s's computer didn't start.", bot_id)

    async def stop(self, org_id: uuid.UUID, bot_id: uuid.UUID, *, idle_since: datetime | None = None) -> bool:
        """Stop the bot's computer (its disk stays) and record its running time. `idle_since`: only
        if nobody used it since then (the idle stop). True when a stop was asked for."""
        async with self.sessionmaker() as db:
            row = await db.scalar(select(BotComputer).where(BotComputer.bot_id == bot_id))
            if row is None or not row.remote_id or row.status in ("stopped", "stopping"):
                return False
            if idle_since is not None:
                used = row.last_used_at or row.started_at
                if row.status != "running" or (used is not None and used >= idle_since):
                    return False  # used since the idle stop looked
            bill(db, row, utcnow(), self.settings)
            row.status = "stopping"
            row_id, remote_id = row.id, row.remote_id
            await db.commit()
        try:
            async with self.watching(org_id):
                await (await self.provider(org_id)).stop(remote_id)
        except Gone:
            await self._forget(row_id)
            return True
        except (ComputerError, MayHaveRun) as error:
            # Still running at Orgo: counted from now, and the idle stop tries again.
            async with self.sessionmaker() as db:
                await db.execute(
                    update(BotComputer)
                    .where(BotComputer.id == row_id)
                    .values(status="running", started_at=utcnow(), error=str(error))
                )
                await db.commit()
            raise
        await self._set_status(row_id, "stopped")
        return True

    async def stop_all(self, org_id: uuid.UUID) -> None:
        """Every running computer of the organization, best effort (removing its key)."""
        async with self.sessionmaker() as db:
            bots = list(await db.scalars(select(BotComputer.bot_id).where(BotComputer.org_id == org_id)))
        for bot_id in bots:
            try:
                await self.stop(org_id, bot_id)
            except Exception as error:
                logger.warning("Bot %s's computer wasn't stopped: %s", bot_id, error)

    async def stop_soon(self, org_id: uuid.UUID, bot_id: uuid.UUID) -> None:
        """Stop it in the background, best effort (the bot was switched back to its browser)."""

        async def stop() -> None:
            try:
                await self.stop(org_id, bot_id)
            except Exception as error:
                logger.warning("Bot %s's computer wasn't stopped: %s", bot_id, error)

        self._spawn(stop())

    async def delete(self, org_id: uuid.UUID, bot_id: uuid.UUID) -> None:
        """Delete the bot's computer at Orgo, with its disk, then forget it."""
        async with self.sessionmaker() as db:
            seen = await db.scalar(select(BotComputer).where(BotComputer.bot_id == bot_id))
            row_id, remote_id = (seen.id, seen.remote_id) if seen else (None, "")
        if row_id is None:
            return
        if remote_id:
            async with self.watching(org_id):
                await (await self.provider(org_id)).delete(remote_id)
        await self._forget(row_id)

    async def leaving(self, db: AsyncSession, org_id: uuid.UUID, bot_id: uuid.UUID) -> Callable[[], Awaitable[None]]:
        """In the transaction that removes the bot: its running time is recorded; after the commit,
        call what this returns to delete its computer at Orgo (best effort)."""
        row = await db.scalar(select(BotComputer).where(BotComputer.bot_id == bot_id))
        if row is None or not row.remote_id:
            return _nothing
        bill(db, row, utcnow(), self.settings)
        provider_row = await find_provider(db, org_id)
        remote_id = row.remote_id
        if provider_row is None:
            return _nothing
        provider = provider_for(_key_of(provider_row, self.vault), self.settings, self.transport)

        async def delete_there() -> None:
            await _quietly(provider.delete(remote_id))

        return delete_there

    async def view(self, org_id: uuid.UUID, bot_id: uuid.UUID) -> ComputerOut:
        """The Computer tab: the row, plus its apps and links when it runs (asked of Orgo)."""
        async with self.sessionmaker() as db:
            row = await db.scalar(select(BotComputer).where(BotComputer.bot_id == bot_id))
        if row is None:
            return ComputerOut(status="none")
        out = view_of(row, self.settings)
        if row.status != "running" or not row.remote_id:
            return out
        try:
            async with self.watching(org_id):
                provider = await self.provider(org_id)
                apps, previews = await asyncio.gather(provider.apps(row.remote_id), provider.previews(row.remote_id))
        except (ComputerError, MayHaveRun):
            return out  # the row still says what's known
        out.apps = [ComputerAppOut(name=app.name, port=app.port, status=app.status) for app in apps]
        out.previews = [ComputerPreviewOut(url=p.url, port=p.port, access=p.access) for p in previews]
        return out

    async def running(self, org_id: uuid.UUID, bot_id: uuid.UUID) -> tuple[ComputerProvider, str]:
        """For watching and taking over: the provider and the computer, which must be running."""
        async with self.sessionmaker() as db:
            remote_id = await db.scalar(
                select(BotComputer.remote_id).where(BotComputer.bot_id == bot_id, BotComputer.status == "running")
            )
        if not remote_id:
            raise NotRunning(NOT_RUNNING)
        return await self.provider(org_id), remote_id

    async def stop_idle(self, now: datetime) -> int:
        """The idle stop (every minute): running computers nobody used for COMPUTER_IDLE_MINUTES."""
        cutoff = now - timedelta(minutes=self.settings.computer_idle_minutes)
        async with self.sessionmaker() as db:
            idle = (
                await db.execute(
                    select(BotComputer.org_id, BotComputer.bot_id).where(
                        BotComputer.status == "running",
                        or_(BotComputer.last_used_at.is_(None), BotComputer.last_used_at < cutoff),
                    )
                )
            ).all()
        stopped = 0
        for org_id, bot_id in idle:
            try:
                stopped += await self.stop(org_id, bot_id, idle_since=cutoff)
            except Exception as error:
                logger.warning("Bot %s's idle computer wasn't stopped: %s", bot_id, error)
        return stopped

    # Background work

    def _spawn(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(work)
        self._background.add(task)  # asyncio keeps only weak references
        task.add_done_callback(self._background.discard)

    async def settle(self) -> None:
        """Wait for background starts and stops (tests; shutting down)."""
        while self._background:
            await asyncio.gather(*list(self._background), return_exceptions=True)


def view_of(row: BotComputer, settings: Settings) -> ComputerOut:
    """Built field by field: nothing of Orgo's own answer (its password, its address) is in it."""
    running = row.status == "running"
    idle_from = row.last_used_at or row.started_at
    return ComputerOut(
        status=row.status,  # only valid statuses are saved
        name=row.name,
        remote_id=row.remote_id or None,
        cpu=row.cpu,
        ram=row.ram,
        region=row.region,
        started_at=row.started_at,
        last_used_at=row.last_used_at,
        idle_stops_at=idle_from + timedelta(minutes=settings.computer_idle_minutes) if running and idle_from else None,
        error=row.error,
        orgo_url=ORGO_COMPUTER_URL.format(id=row.remote_id) if row.remote_id else None,
    )


def _copy_size(row: BotComputer, remote: RemoteComputer) -> None:
    row.cpu = remote.cpu if remote.cpu is not None else row.cpu
    row.ram = remote.ram if remote.ram is not None else row.ram
    row.region = remote.region or row.region


async def _nothing() -> None:
    return None


async def _quietly(work: Awaitable[None]) -> None:
    try:
        await work
    except (ComputerError, MayHaveRun) as error:
        logger.warning("Orgo didn't delete a computer: %s", error)
