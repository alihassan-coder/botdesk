"""Prices that change on a known date switch by themselves: the price used is the one in effect
when the call is made (docs/ROADMAP.md lists the changes)."""

from datetime import UTC, datetime, timedelta, timezone

from src.model_providers import Pricing
from src.services import pricing

BEFORE_DECEMBER = datetime(2026, 11, 30, 23, 59, tzinfo=UTC)
DECEMBER_FIRST = datetime(2026, 12, 1, 0, 0, tzinfo=UTC)
BEFORE_JANUARY = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
JANUARY_FIRST = datetime(2027, 1, 1, 0, 0, tzinfo=UTC)


def test_gemini_4_carbon_and_argon_double_on_december_first() -> None:
    for model in ("gemini-4-carbon", "gemini-4-argon"):
        assert pricing.table_price("gemini", model, at=BEFORE_DECEMBER) == Pricing(2.0, 10.0)
        assert pricing.table_price("gemini", model, at=DECEMBER_FIRST) == Pricing(4.0, 20.0)


def test_gemini_2_5_pro_and_flash_have_no_price_once_they_switch_models() -> None:
    assert pricing.table_price("gemini", "gemini-2.5-pro", at=BEFORE_DECEMBER) == Pricing(1.25, 10.0)
    assert pricing.table_price("gemini", "models/gemini-2.5-flash", at=BEFORE_DECEMBER) == Pricing(0.30, 2.50)
    assert pricing.table_price("gemini", "gemini-2.5-pro", at=DECEMBER_FIRST) is None
    assert pricing.table_price("gemini", "gemini-2.5-flash", at=DECEMBER_FIRST) is None
    # Its sibling isn't affected.
    assert pricing.table_price("gemini", "gemini-2.5-flash-lite", at=DECEMBER_FIRST) == Pricing(0.10, 0.40)


def test_gemini_3_8_flash_doubles_on_january_first() -> None:
    assert pricing.table_price("gemini", "gemini-3.8-flash", at=BEFORE_JANUARY) == Pricing(0.75, 3.75)
    assert pricing.table_price("gemini", "gemini-3.8-flash", at=JANUARY_FIRST) == Pricing(1.50, 7.50)


def test_a_change_takes_effect_at_utc_midnight_whatever_the_time_zone_of_the_moment() -> None:
    karachi = timezone(timedelta(hours=5))
    # 04:59 in Karachi on 1 December is still 30 November in UTC.
    assert pricing.table_price("gemini", "gemini-4-carbon", at=datetime(2026, 12, 1, 4, 59, tzinfo=karachi)) == Pricing(
        2.0, 10.0
    )


def test_unchanged_models_keep_their_price_and_the_default_moment_is_now() -> None:
    assert pricing.table_price("anthropic", "claude-sonnet-5-5", at=JANUARY_FIRST) == Pricing(2.0, 10.0)
    assert pricing.table_price("anthropic", "claude-sonnet-5-5") == Pricing(2.0, 10.0)
