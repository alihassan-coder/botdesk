"""Runs record usage after each model call and stop before one that would pass a budget (real Postgres)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGenerationChunk
from sqlalchemy import select

from src.model_providers import Pricing
from src.models import UsageRecord
from src.runtime.chat_model import ModelPrice
from tests.conftest import Postgres
from tests.test_runs_postgres import ScriptedModel, _bot_chat, _events, _send, use_model


class CountingModel(ScriptedModel):
    """Streams its tokens, then reports token counts in a last chunk, as providers do when streaming."""

    usage: UsageMetadata | None = None

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
            yield chunk
        if self.usage:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=self.usage))


def use_price(pg: Postgres, pricing: Pricing | None, model_id: str = "anthropic:claude-sonnet-5-5") -> None:
    async def price_for(_org_id: uuid.UUID, _model_id: str) -> ModelPrice:
        return ModelPrice(model_id=model_id, provider=model_id.partition(":")[0], pricing=pricing)

    pg.runs.price_for = price_for


USAGE = UsageMetadata(input_tokens=1200, output_tokens=300, total_tokens=1500)


async def _records(pg: Postgres) -> list[UsageRecord]:
    async with pg.runs.sessionmaker() as db:
        return list(await db.scalars(select(UsageRecord).order_by(UsageRecord.created_at)))


async def test_each_model_call_records_its_tokens_and_cost(pg: Postgres) -> None:
    use_model(pg, CountingModel(tokens=["Hi", "!"], usage=USAGE))
    use_price(pg, Pricing(input_per_mtok=2.0, output_per_mtok=10.0))
    org, thread = await _bot_chat(pg.client)

    run_id = await _send(pg.client, thread, "Hello")
    await pg.runs.wait_until_idle()

    records = await _records(pg)
    assert len(records) == 1
    record = records[0]
    assert str(record.run_id) == run_id
    assert (record.provider, record.model_id) == ("anthropic", "anthropic:claude-sonnet-5-5")
    assert (record.input_tokens, record.output_tokens) == (1200, 300)
    assert record.cost_usd is not None and abs(record.cost_usd - (0.0024 + 0.003)) < 1e-9

    usage = (await pg.client.get(f"{org}/usage")).json()
    assert abs(usage["monthToDateUsd"] - 0.0054) < 1e-9
    assert usage["days"][-1]["inputTokens"] == 1200  # today, grouped by UTC day on Postgres
    assert abs(usage["bots"][0]["spentUsd"] - 0.0054) < 1e-9


async def test_a_model_with_an_unknown_price_records_tokens_and_no_cost(pg: Postgres) -> None:
    use_model(pg, CountingModel(usage=USAGE))
    use_price(pg, None, model_id="custom-1:llama3.2")
    org, thread = await _bot_chat(pg.client)

    await _send(pg.client, thread, "Hello")
    await pg.runs.wait_until_idle()

    [record] = await _records(pg)
    assert record.cost_usd is None and record.input_tokens == 1200
    usage = (await pg.client.get(f"{org}/usage")).json()
    assert usage["monthToDateUsd"] == 0.0
    assert usage["unpricedTokens"] == 1500


async def test_a_model_that_reports_no_tokens_records_nothing(pg: Postgres) -> None:
    use_model(pg, CountingModel(usage=None))
    _org, thread = await _bot_chat(pg.client)

    await _send(pg.client, thread, "Hello")
    await pg.runs.wait_until_idle()

    assert await _records(pg) == []


async def _spend(pg: Postgres, org: str, bot_id: str | None, cost: float) -> None:
    async with pg.runs.sessionmaker() as db:
        db.add(
            UsageRecord(
                org_id=uuid.UUID(org.rsplit("/", 1)[1]),
                bot_id=uuid.UUID(bot_id) if bot_id else None,
                provider="anthropic",
                model_id="anthropic:claude-sonnet-5-5",
                input_tokens=1,
                output_tokens=1,
                cost_usd=cost,
                created_at=datetime.now(UTC),
            )
        )
        await db.commit()


async def _bot_id(pg: Postgres, org: str) -> str:
    bot_id: str = (await pg.client.get(f"{org}/bots")).json()[0]["id"]
    return bot_id


async def test_a_bot_over_its_budget_stops_before_calling_the_model(pg: Postgres) -> None:
    model = CountingModel(usage=USAGE)
    use_model(pg, model)
    use_price(pg, Pricing(input_per_mtok=2.0, output_per_mtok=10.0))
    org, thread = await _bot_chat(pg.client)
    bot_id = await _bot_id(pg, org)
    await pg.client.patch(f"{org}/bots/{bot_id}", json={"monthlyBudgetUsd": 40})
    await _spend(pg, org, bot_id, 40.0)

    run_id = await _send(pg.client, thread, "Hello")
    await pg.runs.wait_until_idle()

    run = (await pg.client.get(f"{org}/runs/{run_id}")).json()
    assert run["status"] == "failed"
    assert run["error"] == "Scout reached its $40 monthly budget. Raise it in the bot's settings."
    assert model.prompts == []  # the model was never called
    failed = [e for e in await _events(pg.client, thread) if e["event"] == "run_failed"]
    assert failed[-1]["data"]["data"] == {"status": "failed", "error": run["error"], "code": "budget"}


async def test_the_organization_budget_stops_runs_too(pg: Postgres) -> None:
    model = CountingModel(usage=USAGE)
    use_model(pg, model)
    use_price(pg, Pricing(input_per_mtok=2.0, output_per_mtok=10.0))
    org, thread = await _bot_chat(pg.client)
    await pg.client.patch(org, json={"monthlyBudgetUsd": 10})
    await _spend(pg, org, None, 10.0)  # spent by a bot that was removed since

    run_id = await _send(pg.client, thread, "Hello")
    await pg.runs.wait_until_idle()

    run = (await pg.client.get(f"{org}/runs/{run_id}")).json()
    assert run["status"] == "failed"
    assert run["error"].endswith(
        "reached its $10 monthly budget for all its bots. An owner or admin can raise it in Settings → Usage & budgets."
    )
    assert model.prompts == []


async def test_a_run_inside_its_budget_carries_on(pg: Postgres) -> None:
    use_model(pg, CountingModel(usage=USAGE))
    use_price(pg, Pricing(input_per_mtok=2.0, output_per_mtok=10.0))
    org, thread = await _bot_chat(pg.client)
    await _spend(pg, org, await _bot_id(pg, org), 10.0)  # default budget is $50

    run_id = await _send(pg.client, thread, "Hello")
    await pg.runs.wait_until_idle()

    assert (await pg.client.get(f"{org}/runs/{run_id}")).json()["status"] == "succeeded"
