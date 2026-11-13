"""Usage and budgets on SQLite: prices, costs, month boundaries, budget checks and the usage routes.
Runs that record usage and stop for budget are in test_usage_postgres.py."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from langchain_core.messages import AIMessageChunk
from langchain_core.messages.ai import UsageMetadata
from langchain_core.runnables import RunnableBinding

from src.model_providers import ModelInfo, Pricing
from src.models import UsageRecord
from src.runtime.chat_model import (
    MIN_OUTPUT_CAP,
    PRICE_RETRY_SECONDS,
    ModelPrice,
    ModelResolver,
    StandInModel,
    cap_output,
    output_cap,
)
from src.runtime.graph import Streamed, TokensUsed, usage_of
from src.services import pricing, provider_service, usage_service
from src.services.model_catalog import ModelCatalog
from src.services.provider_service import Connection
from tests.conftest import TEST_SETTINGS, FakeProviders, api_client, sign_up

# Prices and costs


def test_the_price_table_knows_common_models_and_drops_date_suffixes() -> None:
    assert pricing.table_price("anthropic", "claude-sonnet-5-5") == Pricing(2.0, 10.0)
    assert pricing.table_price("anthropic", "claude-sonnet-4-5-20250929") == Pricing(3.0, 15.0)
    assert pricing.table_price("openai", "gpt-4o-2024-08-06") == Pricing(2.50, 10.0)
    assert pricing.table_price("gemini", "models/gemini-2.5-flash") == Pricing(0.30, 2.50)
    assert pricing.table_price("groq", "openai/gpt-oss-120b") == Pricing(0.15, 0.60)


def test_a_model_missing_from_the_table_has_an_unknown_price() -> None:
    assert pricing.table_price("openai", "gpt-4o-mini-but-new") is None
    assert pricing.table_price("anthropic", "claude-unreleased") is None
    assert pricing.table_price("custom", "llama3.2") is None


def test_cost_is_tokens_times_the_price_per_million() -> None:
    price = Pricing(input_per_mtok=3.0, output_per_mtok=15.0)
    assert pricing.cost_usd(price, 1_000_000, 0) == pytest.approx(3.0)
    assert pricing.cost_usd(price, 2_000, 500) == pytest.approx(0.006 + 0.0075)
    assert pricing.cost_usd(None, 2_000, 500) is None


def test_the_estimate_before_a_call_is_small_and_zero_without_a_price() -> None:
    price = Pricing(input_per_mtok=3.0, output_per_mtok=15.0)
    # 4,000 characters ≈ 1,000 input tokens, plus a 500-token answer.
    assert pricing.estimate_usd(price, 4_000) == pytest.approx(0.003 + 0.0075)
    assert pricing.estimate_usd(None, 4_000) == 0.0


@pytest.mark.parametrize(
    ("now", "start"),
    [
        (datetime(2026, 11, 13, 15, 30, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)),
        (datetime(2026, 12, 1, 0, 0, tzinfo=UTC), datetime(2026, 12, 1, tzinfo=UTC)),
        # 23:30 on Nov 30 in New York is already December 1st in UTC.
        (datetime(2026, 11, 30, 23, 30, tzinfo=UTC) + timedelta(hours=5), datetime(2026, 12, 1, tzinfo=UTC)),
    ],
)
def test_months_start_at_midnight_utc_on_the_first(now: datetime, start: datetime) -> None:
    assert usage_service.month_start(now) == start


# On SQLite: budgets and the usage routes


@dataclass
class Org:
    app: FastAPI
    client: httpx.AsyncClient
    path: str
    id: uuid.UUID
    bots: dict[str, str]  # name → id

    async def add_usage(
        self, bot: str | None, cost: float | None, at: datetime, *, tokens: tuple[int, int] = (1000, 200)
    ) -> None:
        async with self.app.state.sessionmaker() as db:
            db.add(
                UsageRecord(
                    org_id=self.id,
                    bot_id=uuid.UUID(self.bots[bot]) if bot else None,
                    provider="anthropic",
                    model_id="anthropic:claude-sonnet-5-5",
                    input_tokens=tokens[0],
                    output_tokens=tokens[1],
                    cost_usd=cost,
                    created_at=at,
                )
            )
            await db.commit()

    async def set_bot_budget(self, bot: str, budget: int) -> None:
        response = await self.client.patch(f"{self.path}/bots/{self.bots[bot]}", json={"monthlyBudgetUsd": budget})
        assert response.status_code == 200, response.text

    async def budget_stop(self, bot: str, now: datetime, estimate: float = 0.01) -> str | None:
        async with self.app.state.sessionmaker() as db:
            return await usage_service.budget_stop(
                db, org_id=self.id, bot_id=uuid.UUID(self.bots[bot]), estimate_usd=estimate, now=now
            )


async def _org(app: FastAPI, client: httpx.AsyncClient, email: str, bots: list[str]) -> Org:
    me = await sign_up(client, email=email)
    org_id = me["organizations"][0]["id"]
    path = f"/api/v1/orgs/{org_id}"
    ids = {}
    for name in bots:
        response = await client.post(f"{path}/bots", json={"name": name, "monthlyBudgetUsd": 40})
        ids[name] = response.json()["id"]
    return Org(app=app, client=client, path=path, id=uuid.UUID(org_id), bots=ids)


@pytest.fixture
async def acme(providers: FakeProviders) -> AsyncIterator[Org]:
    async with api_client(TEST_SETTINGS, providers) as (app, client):
        yield await _org(app, client, "ali@acme.dev", ["Inbox Manager", "Scout"])


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


async def test_a_bot_over_its_budget_is_stopped_with_a_clear_message(acme: Org) -> None:
    await acme.add_usage("Inbox Manager", 39.995, NOW - timedelta(days=2))

    assert await acme.budget_stop("Inbox Manager", NOW, estimate=0.001) is None
    assert await acme.budget_stop("Inbox Manager", NOW, estimate=0.01) == (
        "Inbox Manager reached its $40 monthly budget. Raise it in the bot's settings."
    )
    assert await acme.budget_stop("Scout", NOW) is None  # each bot has its own budget


async def test_a_budget_of_zero_means_no_limit(acme: Org) -> None:
    await acme.add_usage("Inbox Manager", 500.0, NOW - timedelta(days=1))
    await acme.set_bot_budget("Inbox Manager", 0)

    assert await acme.budget_stop("Inbox Manager", NOW) is None


async def test_spend_from_last_month_does_not_count(acme: Org) -> None:
    first = datetime(2026, 12, 1, tzinfo=UTC)
    await acme.add_usage("Inbox Manager", 45.0, first - timedelta(seconds=1))  # Nov 30, 23:59:59 UTC

    assert await acme.budget_stop("Inbox Manager", first) is None
    await acme.add_usage("Inbox Manager", 45.0, first)  # Dec 1, 00:00 UTC
    assert await acme.budget_stop("Inbox Manager", first + timedelta(minutes=1)) is not None


async def test_the_organization_budget_stops_every_bot(acme: Org) -> None:
    await acme.add_usage("Inbox Manager", 30.0, NOW - timedelta(days=1))
    await acme.add_usage("Scout", 30.0, NOW - timedelta(days=1))
    await acme.add_usage(None, 15.0, NOW - timedelta(days=1))  # a bot removed this month still counts
    response = await acme.client.patch(acme.path, json={"monthlyBudgetUsd": 75})
    assert response.status_code == 200, response.text
    assert response.json()["monthlyBudgetUsd"] == 75

    message = await acme.budget_stop("Scout", NOW)

    assert message is not None and message.startswith("Ali's team reached its $75 monthly budget for all its bots.")


async def test_only_owners_and_admins_change_the_organization_budget(acme: Org) -> None:
    assert (await acme.client.patch(acme.path, json={"monthlyBudgetUsd": 100})).json()["monthlyBudgetUsd"] == 100
    assert (await acme.client.patch(acme.path, json={"name": "Acme"})).json()["monthlyBudgetUsd"] == 100  # kept
    assert (await acme.client.patch(acme.path, json={"monthlyBudgetUsd": None})).json()["monthlyBudgetUsd"] is None
    assert (await acme.client.patch(acme.path, json={"monthlyBudgetUsd": 0})).json()["monthlyBudgetUsd"] is None
    assert (await acme.client.patch(acme.path, json={"monthlyBudgetUsd": -5})).status_code == 422

    invite = await acme.client.post(f"{acme.path}/invitations", json={"email": "sara@acme.dev", "role": "member"})
    assert invite.status_code == 201, invite.text
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=acme.app), base_url="http://test") as sara:
        await sign_up(sara, name="Sara", email="sara@acme.dev")
        assert (await sara.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200

        assert (await sara.get(f"{acme.path}/usage")).status_code == 200  # any member sees usage
        assert (await sara.get(f"{acme.path}/bots/{acme.bots['Scout']}/usage")).status_code == 200
        assert (await sara.patch(acme.path, json={"monthlyBudgetUsd": 1})).status_code == 403


async def test_usage_shows_daily_totals_this_month_and_each_bots_budget(acme: Org) -> None:
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    await acme.add_usage("Inbox Manager", 1.25, today + timedelta(minutes=1))
    await acme.add_usage("Inbox Manager", 0.75, today + timedelta(minutes=2))
    await acme.add_usage("Scout", None, today + timedelta(minutes=3), tokens=(800, 200))  # unknown price
    await acme.add_usage("Scout", 2.0, today - timedelta(days=2))
    await acme.add_usage("Scout", 9.0, today - timedelta(days=40))  # outside the chart and the month

    response = await acme.client.get(f"{acme.path}/usage", params={"days": 3})

    assert response.status_code == 200, response.text
    usage = response.json()
    assert [day["date"] for day in usage["days"]] == [
        (today - timedelta(days=offset)).date().isoformat() for offset in (2, 1, 0)
    ]
    assert usage["days"][0]["modelsUsd"] == pytest.approx(2.0)
    assert usage["days"][1] == {
        "date": (today - timedelta(days=1)).date().isoformat(),
        "modelsUsd": 0.0,
        "computersUsd": 0.0,
        "inputTokens": 0,
        "outputTokens": 0,
        "unpricedTokens": 0,
    }
    assert usage["days"][2]["modelsUsd"] == pytest.approx(2.0)
    assert usage["days"][2]["unpricedTokens"] == 1000
    assert usage["monthStart"] == today.replace(day=1).date().isoformat()
    in_month = 2.0 + (2.0 if (today - timedelta(days=2)).month == today.month else 0.0)
    assert usage["monthToDateUsd"] == pytest.approx(in_month)
    assert usage["orgBudgetUsd"] is None
    assert usage["pricesChecked"] == pricing.PRICES_CHECKED
    inbox = next(bot for bot in usage["bots"] if bot["name"] == "Inbox Manager")
    assert inbox["spentUsd"] == pytest.approx(2.0)
    assert inbox["budgetUsd"] == 40
    assert inbox["inputTokens"] == 2000

    scout = await acme.client.get(f"{acme.path}/bots/{acme.bots['Scout']}/usage", params={"days": 3})
    assert scout.status_code == 200, scout.text
    assert scout.json()["unpricedTokens"] == 1000
    assert [day["modelsUsd"] for day in scout.json()["days"]] == [pytest.approx(2.0), 0.0, 0.0]


async def test_a_bot_with_no_budget_shows_none(acme: Org) -> None:
    await acme.set_bot_budget("Scout", 0)
    usage = (await acme.client.get(f"{acme.path}/usage")).json()
    assert len(usage["days"]) == 14
    assert next(bot for bot in usage["bots"] if bot["name"] == "Scout")["budgetUsd"] is None


async def test_usage_stays_inside_its_organization(acme: Org) -> None:
    await acme.add_usage("Inbox Manager", 5.0, datetime.now(UTC))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=acme.app), base_url="http://test") as other:
        globex = await _org(acme.app, other, "omar@globex.dev", ["Helper"])

        mine = (await other.get(f"{globex.path}/usage")).json()
        assert mine["monthToDateUsd"] == 0.0
        assert [bot["name"] for bot in mine["bots"]] == ["Helper"]
        assert (await other.get(f"{acme.path}/usage")).status_code in (403, 404)
        assert (await other.get(f"{acme.path}/bots/{acme.bots['Scout']}/usage")).status_code in (403, 404)
        # A bot of another organization isn't found through yours.
        assert (await other.get(f"{globex.path}/bots/{acme.bots['Scout']}/usage")).status_code == 404


async def test_days_are_limited(acme: Org) -> None:
    assert (await acme.client.get(f"{acme.path}/usage", params={"days": 0})).status_code == 422
    assert (await acme.client.get(f"{acme.path}/usage", params={"days": 91})).status_code == 422


# Where a run's prices come from


async def test_prices_come_from_the_table_from_openrouters_list_or_nowhere(acme: Org) -> None:
    resolver = ModelResolver(TEST_SETTINGS, acme.app.state.sessionmaker, acme.app.state.secrets, acme.app.state.models)
    acme.app.state.models.remember(
        acme.id,
        Connection("openrouter", "openrouter", "OpenRouter", "sk-or-test"),
        [ModelInfo("meta/llama-4", "Llama 4", pricing=Pricing(0.2, 0.6))],
    )

    anthropic = await resolver.price(acme.id, "anthropic:claude-haiku-5-5")
    assert (anthropic.provider, anthropic.pricing) == ("anthropic", Pricing(0.10, 0.50))
    openrouter = await resolver.price(acme.id, "openrouter:meta/llama-4")
    assert openrouter.pricing == Pricing(0.2, 0.6)
    assert (await resolver.price(acme.id, "openrouter:not/listed")).pricing is None
    custom = await resolver.price(acme.id, f"custom-{uuid.uuid4()}:llama3.2:latest")
    assert custom.pricing is None and custom.provider.startswith("custom-")
    default = await resolver.price(acme.id, "")
    assert default.model_id == TEST_SETTINGS.default_model_id


async def test_removing_a_bot_keeps_its_spend_in_the_organization(acme: Org) -> None:
    await acme.add_usage("Scout", 3.0, datetime.now(UTC))
    assert (await acme.client.delete(f"{acme.path}/bots/{acme.bots['Scout']}")).status_code == 204

    usage = (await acme.client.get(f"{acme.path}/usage")).json()
    assert usage["monthToDateUsd"] == pytest.approx(3.0)
    assert [bot["name"] for bot in usage["bots"]] == ["Inbox Manager"]


# A failure fetching OpenRouter's prices is remembered, and one fetch serves every waiting run


class SlowCatalog:
    """Stands in for `ModelCatalog`: counts fetches, which fail or answer after a short wait."""

    def __init__(self, *, fail: bool) -> None:
        self.fail = fail
        self.fetches = 0
        self.list: list[ModelInfo] | None = None

    def cached(self, _org_id: uuid.UUID, _provider_id: str) -> list[ModelInfo] | None:
        return self.list

    async def models(self, _org_id: uuid.UUID, _connection: Connection) -> list[ModelInfo]:
        self.fetches += 1
        await asyncio.sleep(0.01)
        if self.fail:
            raise httpx.ConnectTimeout("too slow")
        self.list = [ModelInfo("meta/llama-4", "Llama 4", pricing=Pricing(0.2, 0.6))]
        return self.list


def _resolver(acme: Org, catalog: SlowCatalog, monkeypatch: pytest.MonkeyPatch, clock: list[float]) -> ModelResolver:
    async def connection_for(*_args: object) -> Connection:
        return Connection("openrouter", "openrouter", "OpenRouter", "sk-or-test")

    monkeypatch.setattr(provider_service, "connection_for", connection_for)
    sessionmaker, secrets = acme.app.state.sessionmaker, acme.app.state.secrets
    return ModelResolver(TEST_SETTINGS, sessionmaker, secrets, cast(ModelCatalog, catalog), clock=lambda: clock[0])


async def test_a_failed_price_lookup_is_not_retried_for_a_minute(acme: Org, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog, clock = SlowCatalog(fail=True), [1000.0]
    resolver = _resolver(acme, catalog, monkeypatch, clock)

    assert (await resolver.price(acme.id, "openrouter:meta/llama-4")).pricing is None
    clock[0] += PRICE_RETRY_SECONDS - 1
    assert (await resolver.price(acme.id, "openrouter:meta/llama-4")).pricing is None
    assert catalog.fetches == 1  # the second run didn't wait for OpenRouter again

    catalog.fail = False
    clock[0] += 2  # the minute is up
    assert (await resolver.price(acme.id, "openrouter:meta/llama-4")).pricing == Pricing(0.2, 0.6)
    assert catalog.fetches == 2


async def test_runs_starting_together_fetch_openrouters_prices_once(acme: Org, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = SlowCatalog(fail=False)
    resolver = _resolver(acme, catalog, monkeypatch, [0.0])

    prices = await asyncio.gather(*(resolver.price(acme.id, "openrouter:meta/llama-4") for _ in range(5)))

    assert catalog.fetches == 1
    assert {price.pricing for price in prices} == {Pricing(0.2, 0.6)}


async def test_saving_a_bot_with_an_openrouter_model_looks_up_its_price(acme: Org, providers: FakeProviders) -> None:
    looked_up: list[str] = []

    async def price_for(_org_id: uuid.UUID, model_id: str) -> ModelPrice:
        looked_up.append(model_id)
        return ModelPrice(model_id, "openrouter", None)

    acme.app.state.runs.price_for = price_for
    providers.answer("openrouter.ai", {"data": []})
    saved = await acme.client.put(f"{acme.path}/providers/openrouter", json={"apiKey": "sk-or-test"})
    assert saved.status_code == 200, saved.text
    scout = f"{acme.path}/bots/{acme.bots['Scout']}"

    response = await acme.client.patch(scout, json={"modelId": "openrouter:meta/llama-4"})

    assert response.status_code == 200, response.text
    assert looked_up == ["openrouter:meta/llama-4"]
    await acme.client.patch(scout, json={"name": "Scout 2"})  # the model didn't change: no lookup
    assert looked_up == ["openrouter:meta/llama-4"]


# Each call's output is capped by what the budget has left


def test_the_output_cap_is_what_the_rest_of_the_budget_pays_for() -> None:
    price = Pricing(input_per_mtok=2.0, output_per_mtok=10.0)
    # $0.03 left; 4,000 prompt characters ≈ 1,000 input tokens = $0.002, so $0.028 buys 2,800 tokens.
    assert output_cap(0.03, price, 4_000) == 2_800
    assert output_cap(0.0001, price, 4_000) == MIN_OUTPUT_CAP  # never less than a short answer
    assert output_cap(500.0, price, 4_000) is None  # plenty left: the model's own limit applies
    assert output_cap(None, price, 4_000) is None  # no budget
    assert output_cap(0.03, None, 4_000) is None  # unknown price


class HeldModel(StandInModel):
    """A model with its own output limit, as ChatAnthropic has."""

    max_tokens: int = 1024


def test_the_cap_is_passed_as_max_tokens_unless_the_model_is_held_lower_already() -> None:
    model = StandInModel()
    capped = cap_output(model, model, 900)
    assert isinstance(capped, RunnableBinding) and capped.kwargs == {"max_tokens": 900}
    assert cap_output(model, model, None) is model

    held = HeldModel()
    assert cap_output(held, held, 2_000) is held  # 1,024 is lower already
    assert cast(RunnableBinding[Any, Any], cap_output(held, held, 500)).kwargs == {"max_tokens": 500}


# What a call records, finished or not


def _streamed(*chunks: AIMessageChunk, complete: bool) -> Streamed:
    streamed = Streamed()
    for chunk in chunks:
        streamed.add(chunk)
    streamed.complete = complete
    return streamed


def test_a_finished_call_records_what_the_provider_reported() -> None:
    usage = UsageMetadata(input_tokens=1200, output_tokens=300, total_tokens=1500)
    done = _streamed(AIMessageChunk(content="Hi"), AIMessageChunk(content="", usage_metadata=usage), complete=True)
    assert usage_of(done, 4_000) == TokensUsed(1200, 300)
    assert usage_of(_streamed(AIMessageChunk(content="Hi"), complete=True), 4_000) is None  # nothing reported


def test_a_call_cut_short_records_an_estimate_of_what_it_streamed() -> None:
    cut = _streamed(AIMessageChunk(content="x" * 41), complete=False)
    assert usage_of(cut, 4_000) == TokensUsed(1_000, 11, estimated=True)
    assert usage_of(_streamed(complete=False), 4_000) is None  # failed before anything came back

    # Input reported at the start, output not yet: the output counts at least what streamed.
    started = UsageMetadata(input_tokens=900, output_tokens=1, total_tokens=901)
    cut = _streamed(
        AIMessageChunk(content="", usage_metadata=started), AIMessageChunk(content="x" * 40), complete=False
    )
    assert usage_of(cut, 4_000) == TokensUsed(900, 10, estimated=True)


# Budgets are money: only owners and admins set them


async def test_a_member_cant_change_a_bots_budget_but_an_admin_can(acme: Org) -> None:
    invite = await acme.client.post(f"{acme.path}/invitations", json={"email": "sara@acme.dev", "role": "member"})
    token = invite.json()["inviteUrl"].rsplit("/", 1)[1]
    scout = f"{acme.path}/bots/{acme.bots['Scout']}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=acme.app), base_url="http://test") as sara:
        await sign_up(sara, name="Sara", email="sara@acme.dev")
        assert (await sara.post("/api/v1/invitations/accept", json={"token": token})).status_code == 200

        refused = await sara.patch(scout, json={"monthlyBudgetUsd": 500})
        assert refused.status_code == 403
        assert refused.json()["detail"] == "Only owners and admins can change budgets."
        # The same budget sent back (as the edit form does) is fine, and so is the rest of the bot.
        kept = await sara.patch(scout, json={"monthlyBudgetUsd": 40, "role": "Researcher"})
        assert kept.status_code == 200, kept.text
        assert (await sara.post(f"{acme.path}/bots", json={"name": "Rich", "monthlyBudgetUsd": 900})).status_code == 403
        assert (
            await sara.post(f"{acme.path}/bots", json={"name": "No limit", "monthlyBudgetUsd": 0})
        ).status_code == 403
        # Up to the default is fine when hiring (templates come with smaller budgets).
        assert (await sara.post(f"{acme.path}/bots", json={"name": "Plain"})).status_code == 201
        assert (await sara.post(f"{acme.path}/bots", json={"name": "Small", "monthlyBudgetUsd": 20})).status_code == 201

    assert (await acme.client.patch(scout, json={"monthlyBudgetUsd": 500})).json()["monthlyBudgetUsd"] == 500
