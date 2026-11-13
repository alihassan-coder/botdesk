"""What a model call costs, in US dollars.

Where prices come from:
- **OpenRouter** says what each model costs in its model list (cached by `ModelCatalog`).
- **Anthropic, OpenAI, Gemini, Groq** don't, so `PRICE_TABLE` below holds the common models.
  Prices change: edit the table when they do, and update `PRICES_CHECKED`.
- **Custom servers** have no price.

A model missing from the table has an unknown price: its calls record tokens and no dollars, and
the web shows "price unknown" rather than a guess. Budgets can't stop what has no price.
"""

import re

from src.model_providers import Pricing

PRICES_CHECKED = "2026-11-13"

# US dollars per million tokens (input, output), standard rates without caching or batch
# discounts. Keys are the provider's model id without a date suffix (see `_base_model`).
PRICE_TABLE: dict[str, dict[str, Pricing]] = {
    # https://platform.claude.com/docs/en/about-claude/pricing
    "anthropic": {
        "claude-fable-5-2": Pricing(8.0, 40.0),
        "claude-mythos-5-2": Pricing(8.0, 40.0),
        "claude-fable-5-1": Pricing(10.0, 50.0),
        "claude-mythos-5-1": Pricing(10.0, 50.0),
        "claude-fable-5": Pricing(10.0, 50.0),
        "claude-mythos-5": Pricing(10.0, 50.0),
        "claude-opus-5-5": Pricing(4.0, 20.0),
        "claude-opus-5": Pricing(5.0, 25.0),
        "claude-opus-4-8": Pricing(5.0, 25.0),
        "claude-opus-4-7": Pricing(5.0, 25.0),
        "claude-opus-4-6": Pricing(5.0, 25.0),
        "claude-opus-4-5": Pricing(5.0, 25.0),
        "claude-sonnet-5-5": Pricing(2.0, 10.0),
        "claude-sonnet-5": Pricing(2.0, 10.0),
        "claude-sonnet-4-6": Pricing(3.0, 15.0),
        "claude-sonnet-4-5": Pricing(3.0, 15.0),
        "claude-haiku-5-5": Pricing(0.10, 0.50),  # prompts up to 100K tokens
        "claude-haiku-4-5": Pricing(1.0, 5.0),
    },
    # https://developers.openai.com/api/docs/pricing (formerly platform.openai.com/docs/pricing)
    "openai": {
        "gpt-6-astra": Pricing(10.0, 50.0),  # prompts up to 272K tokens
        "gpt-6.1-sol": Pricing(2.0, 10.0),  # prompts up to 272K tokens
        "gpt-6.1-terra": Pricing(1.0, 5.0),  # prompts up to 272K tokens
        "gpt-6-luna": Pricing(0.10, 0.50),  # prompts up to 272K tokens
        "gpt-5.5": Pricing(5.0, 30.0),  # prompts up to 272K tokens
        "gpt-5.4": Pricing(2.50, 15.0),  # prompts up to 272K tokens
        "gpt-5.4-mini": Pricing(0.75, 4.50),
        "gpt-5.4-nano": Pricing(0.20, 1.25),
        "gpt-5": Pricing(1.25, 10.0),
        "gpt-5-mini": Pricing(0.25, 2.0),
        "gpt-5-nano": Pricing(0.05, 0.40),
        "gpt-4.1": Pricing(2.0, 8.0),
        "gpt-4.1-mini": Pricing(0.40, 1.60),
        "gpt-4o": Pricing(2.50, 10.0),
        "gpt-4o-mini": Pricing(0.15, 0.60),
        "o3": Pricing(2.0, 8.0),
    },
    # https://ai.google.dev/gemini-api/docs/pricing (now served at aistudio.google.com/docs/pricing)
    "gemini": {
        "gemini-4-carbon": Pricing(2.0, 10.0),  # rises to $4 / $20 on 2026-12-01
        "gemini-4-argon": Pricing(2.0, 10.0),  # rises to $4 / $20 on 2026-12-01
        "gemini-4-hydrogen": Pricing(1.50, 7.50),
        "gemini-3.8-flash": Pricing(0.75, 3.75),  # rises to $1.50 / $7.50 on 2027-01-01
        "gemini-3.5-flash-lite": Pricing(0.30, 2.50),
        "gemini-3.1-pro-preview": Pricing(2.0, 12.0),  # prompts up to 200K tokens
        "gemini-3.1-flash-lite": Pricing(0.25, 1.50),  # text, image and video input
        "gemini-2.5-pro": Pricing(1.25, 10.0),  # prompts up to 200K; deprecated, routes to 3.8 Flash on 2026-12-01
        "gemini-2.5-flash": Pricing(0.30, 2.50),  # deprecated, routes to 3.5 Flash-Lite on 2026-12-01
        "gemini-2.5-flash-lite": Pricing(0.10, 0.40),
    },
    # https://console.groq.com/docs/models (groq.com/pricing links here for per-model prices)
    "groq": {
        "openai/gpt-oss-120b": Pricing(0.15, 0.60),
        "openai/gpt-oss-20b": Pricing(0.075, 0.30),
        "qwen/qwen3.8-27b": Pricing(0.80, 4.0),
    },
}

# "claude-sonnet-4-5-20250929", "gpt-4o-2024-08-06", "claude-3-5-haiku-latest" → the base id.
_DATE_SUFFIX = re.compile(r"-(\d{8}|\d{4}-\d{2}-\d{2}|latest)$")

# Before a call we don't know how long the answer will be; budgets count this many output tokens.
ESTIMATED_OUTPUT_TOKENS = 500
CHARS_PER_TOKEN = 4  # a rough rule for English text; only used for the estimate before a call


def _base_model(model: str) -> str:
    return _DATE_SUFFIX.sub("", model.removeprefix("models/"))


def table_price(provider_kind: str, model: str) -> Pricing | None:
    """The price from `PRICE_TABLE`, or None when the model isn't in it (an unknown price).
    Only an exact match (after dropping a date suffix) counts: "gpt-4o" never prices "gpt-4o-mini"."""
    return PRICE_TABLE.get(provider_kind, {}).get(_base_model(model))


def cost_usd(pricing: Pricing | None, input_tokens: int, output_tokens: int) -> float | None:
    """What these tokens cost, or None when the price is unknown."""
    if pricing is None:
        return None
    return (input_tokens * pricing.input_per_mtok + output_tokens * pricing.output_per_mtok) / 1_000_000


def estimate_usd(pricing: Pricing | None, prompt_chars: int) -> float:
    """A small, cautious guess at a call's cost before it's made: the prompt, plus a short answer.
    Zero when the price is unknown."""
    return cost_usd(pricing, prompt_chars // CHARS_PER_TOKEN, ESTIMATED_OUTPUT_TOKENS) or 0.0
