import uuid
from datetime import date

from src.schemas.common import ApiModel


class UsageDayOut(ApiModel):
    """One UTC day. `computersUsd` stays 0 until bots have computers."""

    date: date
    models_usd: float
    computers_usd: float = 0.0
    input_tokens: int
    output_tokens: int
    # Tokens of models with no known price (custom servers, models missing from the price table).
    unpriced_tokens: int


class BotSpendOut(ApiModel):
    """A bot's spend this calendar month (UTC) against its budget. `budgetUsd` None = no limit."""

    bot_id: uuid.UUID
    name: str
    spent_usd: float
    budget_usd: int | None
    input_tokens: int
    output_tokens: int
    unpriced_tokens: int


class UsageOut(ApiModel):
    """Settings → Usage & budgets."""

    days: list[UsageDayOut]  # oldest first, every day present (zeros on quiet days)
    month_start: date
    month_to_date_usd: float
    org_budget_usd: int | None  # None = no limit
    unpriced_tokens: int  # this month
    bots: list[BotSpendOut]
    prices_checked: str  # when the built-in price table was last checked


class BotUsageOut(BotSpendOut):
    days: list[UsageDayOut]
    month_start: date
