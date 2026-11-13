"""Usage and budgets (agents-and-plugins.md §4.2): record each model call, sum what was spent,
and stop a run before a call that would go over the bot's or the organization's monthly budget.

Months are calendar months in UTC. A budget of 0 (bots) or None (organizations) means no limit.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Bot, Organization, UsageRecord
from src.schemas.usage import BotSpendOut, BotUsageOut, UsageDayOut, UsageOut
from src.services.pricing import PRICES_CHECKED

MAX_DAYS = 90


def month_start(now: datetime) -> datetime:
    """Midnight UTC on the first day of `now`'s month (in UTC)."""
    now = now.astimezone(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _money(value: float | None) -> float:
    return round(float(value or 0.0), 6)


# Recording


def record(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    bot_id: uuid.UUID,
    run_id: uuid.UUID,
    provider: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float | None,
) -> UsageRecord:
    """Add one model call's usage. The caller commits (one short insert, outside any long transaction)."""
    row = UsageRecord(
        org_id=org_id,
        bot_id=bot_id,
        run_id=run_id,
        kind="model",
        provider=provider,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )
    db.add(row)
    return row


# Budgets


@dataclass(frozen=True)
class MonthSpend:
    bot_usd: float
    org_usd: float


async def month_spend(db: AsyncSession, org_id: uuid.UUID, bot_id: uuid.UUID, now: datetime) -> MonthSpend:
    """What the bot and its organization spent since the start of this month: one SUM query
    over the (org_id, created_at) index."""
    row = (
        await db.execute(
            select(
                func.sum(case((UsageRecord.bot_id == bot_id, UsageRecord.cost_usd), else_=0.0)),
                func.sum(UsageRecord.cost_usd),
            ).where(UsageRecord.org_id == org_id, UsageRecord.created_at >= month_start(now))
        )
    ).one()
    return MonthSpend(bot_usd=_money(row[0]), org_usd=_money(row[1]))


def bot_budget_message(bot_name: str, budget: int) -> str:
    return f"{bot_name} reached its ${budget} monthly budget. Raise it in the bot's settings."


def org_budget_message(org_name: str, budget: int) -> str:
    return (
        f"{org_name} reached its ${budget} monthly budget for all its bots. "
        "An owner or admin can raise it in Settings → Usage & budgets."
    )


def _over(spent: float, estimate: float, budget: int) -> bool:
    """Stop once the budget is used up, or this call would pass it."""
    return spent >= budget or spent + estimate > budget


async def budget_stop(
    db: AsyncSession, *, org_id: uuid.UUID, bot_id: uuid.UUID, estimate_usd: float, now: datetime
) -> str | None:
    """Checked before each model call. Why the run must stop for money, or None to carry on."""
    limits = (
        await db.execute(
            select(Bot.name, Bot.monthly_budget_usd, Organization.name, Organization.monthly_budget_usd)
            .join(Organization, Organization.id == Bot.org_id)
            .where(Bot.id == bot_id, Bot.org_id == org_id)
        )
    ).first()
    if limits is None:
        return None
    bot_name, bot_budget, org_name, org_budget = limits
    if not bot_budget and not org_budget:
        return None  # no limits: skip the sum
    spent = await month_spend(db, org_id, bot_id, now)
    if bot_budget and _over(spent.bot_usd, estimate_usd, bot_budget):
        return bot_budget_message(bot_name, bot_budget)
    if org_budget and _over(spent.org_usd, estimate_usd, org_budget):
        return org_budget_message(org_name, org_budget)
    return None


# Reports


def _utc_day(db: AsyncSession) -> ColumnElement[Any]:
    """The UTC calendar day of a record. Postgres converts explicitly (its `date()` uses the
    session's time zone); SQLite stores UTC text already."""
    if db.get_bind().dialect.name == "postgresql":
        return func.date(func.timezone("UTC", UsageRecord.created_at))
    return func.date(UsageRecord.created_at)


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


_UNPRICED = case((UsageRecord.cost_usd.is_(None), UsageRecord.input_tokens + UsageRecord.output_tokens), else_=0)


def _clamp_days(days: int) -> int:
    return max(1, min(days, MAX_DAYS))


async def _days(
    db: AsyncSession, org_id: uuid.UUID, days: int, now: datetime, *, bot_id: uuid.UUID | None = None
) -> list[UsageDayOut]:
    """Daily totals for the last `days` UTC days, today included, oldest first, quiet days as zeros."""
    today = now.astimezone(UTC).date()
    first = today - timedelta(days=_clamp_days(days) - 1)
    day = _utc_day(db)
    query = (
        select(
            day,
            func.sum(UsageRecord.cost_usd),
            func.sum(UsageRecord.input_tokens),
            func.sum(UsageRecord.output_tokens),
            func.sum(_UNPRICED),
        )
        .where(
            UsageRecord.org_id == org_id,
            UsageRecord.created_at >= datetime(first.year, first.month, first.day, tzinfo=UTC),
        )
        .group_by(day)
    )
    if bot_id is not None:
        query = query.where(UsageRecord.bot_id == bot_id)
    found = {_as_date(row[0]): row for row in await db.execute(query)}
    out: list[UsageDayOut] = []
    for offset in range((today - first).days + 1):
        current = first + timedelta(days=offset)
        row = found.get(current)
        out.append(
            UsageDayOut(
                date=current,
                models_usd=_money(row[1]) if row else 0.0,
                input_tokens=int(row[2] or 0) if row else 0,
                output_tokens=int(row[3] or 0) if row else 0,
                unpriced_tokens=int(row[4] or 0) if row else 0,
            )
        )
    return out


async def _month_by_bot(
    db: AsyncSession, org_id: uuid.UUID, now: datetime, *, bot_id: uuid.UUID | None = None
) -> dict[uuid.UUID | None, Any]:
    query = (
        select(
            UsageRecord.bot_id,
            func.sum(UsageRecord.cost_usd),
            func.sum(UsageRecord.input_tokens),
            func.sum(UsageRecord.output_tokens),
            func.sum(_UNPRICED),
        )
        .where(UsageRecord.org_id == org_id, UsageRecord.created_at >= month_start(now))
        .group_by(UsageRecord.bot_id)
    )
    if bot_id is not None:
        query = query.where(UsageRecord.bot_id == bot_id)
    return {row[0]: row for row in await db.execute(query)}


def _bot_spend(bot: Bot, row: Any) -> BotSpendOut:
    return BotSpendOut(
        bot_id=bot.id,
        name=bot.name,
        spent_usd=_money(row[1]) if row else 0.0,
        budget_usd=bot.monthly_budget_usd or None,
        input_tokens=int(row[2] or 0) if row else 0,
        output_tokens=int(row[3] or 0) if row else 0,
        unpriced_tokens=int(row[4] or 0) if row else 0,
    )


async def org_report(db: AsyncSession, org: Organization, bots: Sequence[Bot], days: int, now: datetime) -> UsageOut:
    by_bot = await _month_by_bot(db, org.id, now)
    return UsageOut(
        days=await _days(db, org.id, days, now),
        month_start=month_start(now).date(),
        # Bots removed this month still count toward the organization's spend.
        month_to_date_usd=_money(sum(float(row[1] or 0.0) for row in by_bot.values())),
        org_budget_usd=org.monthly_budget_usd or None,
        unpriced_tokens=sum(int(row[4] or 0) for row in by_bot.values()),
        bots=[_bot_spend(bot, by_bot.get(bot.id)) for bot in bots],
        prices_checked=PRICES_CHECKED,
    )


async def bot_report(db: AsyncSession, org_id: uuid.UUID, bot: Bot, days: int, now: datetime) -> BotUsageOut:
    by_bot = await _month_by_bot(db, org_id, now, bot_id=bot.id)
    spend = _bot_spend(bot, by_bot.get(bot.id))
    return BotUsageOut(
        **spend.model_dump(),
        days=await _days(db, org_id, days, now, bot_id=bot.id),
        month_start=month_start(now).date(),
    )
