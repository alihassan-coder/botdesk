"""The job worker as its own process, for WORKER_MODE=separate on Postgres (ADR 0013):
`python -m src.worker` from apps/api (`pnpm worker` does the same). It runs bot runs, approval
expiry and every other job, and stops cleanly on Ctrl+C or SIGTERM (running jobs get a few
seconds, then go back in the queue). Run the API with WORKER_MODE=separate next to it.
"""

import asyncio
import logging

import httpx

from src.core.config import get_settings
from src.core.database import create_engine, create_sessionmaker
from src.core.secrets import build_secret_box
from src.core.url_guard import GuardedTransport
from src.jobs.background import background
from src.jobs.postgres import ProcrastinateQueue
from src.runtime.memory import build_memory
from src.services.credential_vault import CredentialVault
from src.services.memory_router import OrgMemory
from src.services.model_catalog import ModelCatalog

OUTBOUND_TIMEOUT = httpx.Timeout(10.0, connect=5.0)  # as in main.py


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
    settings = get_settings()
    secrets = build_secret_box(settings)
    engine = create_engine(settings.sqlalchemy_url)
    sessionmaker = create_sessionmaker(engine)
    allow_private = settings.allow_private_model_urls
    try:
        async with (
            httpx.AsyncClient(timeout=OUTBOUND_TIMEOUT) as http,
            httpx.AsyncClient(
                timeout=OUTBOUND_TIMEOUT,
                transport=GuardedTransport(allow_private=allow_private),
                follow_redirects=False,
            ) as custom,
            background(
                settings,
                sessionmaker,
                OrgMemory(build_memory(settings), sessionmaker, settings, CredentialVault.from_settings(settings)),
                secrets,
                ModelCatalog(http, allow_private_urls=allow_private, custom_http=custom),
                role="worker",
            ) as env,
        ):
            assert isinstance(env.queue, ProcrastinateQueue)  # `background` refuses SQLite for a worker
            await env.queue.run_worker(env, concurrency=settings.worker_concurrency, own_signals=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
