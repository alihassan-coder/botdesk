"""The new-email trigger on real Postgres (slice 6.3): `seen` is JSONB, and two polls racing for
one subscription (two workers, or a late job) post each email once: the second finds the row's
cursor already moved under its lock and does nothing."""

import asyncio

import pytest
from sqlalchemy import select

from src.models import Message, Run, TriggerSubscription
from tests.conftest import TEST_DATABASE_URL, _empty_database
from tests.test_gmail_trigger import INVOICE, ME, _on_and_baselined, _poll, history
from tests.test_oauth import GOOGLE_SETTINGS, acme


@pytest.fixture
async def on_postgres() -> None:
    if not TEST_DATABASE_URL:
        pytest.skip("Postgres test: set TEST_DATABASE_URL to run it (see docs/backend/README.md)")
    await _empty_database(TEST_DATABASE_URL)


@pytest.mark.usefixtures("on_postgres")
async def test_two_polls_racing_post_a_new_email_once() -> None:
    assert TEST_DATABASE_URL
    async with acme(GOOGLE_SETTINGS.model_copy(update={"database_url": TEST_DATABASE_URL})) as team:
        await _on_and_baselined(team)
        team.google.gmail = {f"{ME}/history": history("18f1a1"), f"{ME}/messages/18f1a1": INVOICE}

        await asyncio.gather(_poll(team), _poll(team))

        async with team.app.state.sessionmaker() as db:
            runs = list(await db.scalars(select(Run)))
            notices = list(await db.scalars(select(Message).where(Message.author_type == "system")))
            (subscription,) = await db.scalars(select(TriggerSubscription))
        assert len(runs) == 1 and runs[0].tainted
        assert len(notices) == 1
        assert subscription.seen == ["18f1a1"] and subscription.cursor == "48410"
