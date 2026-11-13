"""Model providers, their keys and their live model lists, as JSON (camelCase).

No response ever carries a key: only `keyHint`, its last 4 characters.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from src.model_providers import ProviderKind
from src.schemas.common import ApiModel


class ProviderOut(ApiModel):
    id: str  # "anthropic" … or "custom-<uuid>"
    kind: ProviderKind
    name: str  # the label, for a custom server
    hint: str
    connected: bool
    # Where the key comes from: this organization (Settings), or the server's environment.
    source: Literal["org", "env"] | None = None
    key_hint: str | None = None
    status: Literal["ok", "invalid"] | None = None
    last_verified_at: datetime | None = None
    base_url: str | None = None


class ProviderKeyIn(ApiModel):
    """Add or replace a key. Custom servers also need a base URL (and a name, the first time);
    their key is optional, since local servers like Ollama take none."""

    api_key: str = Field(default="", max_length=500)
    base_url: str | None = Field(default=None, max_length=500)
    label: str | None = Field(default=None, max_length=80)


class ProviderTestOut(ApiModel):
    ok: bool
    error: str | None = None
    provider: ProviderOut


class PricingOut(ApiModel):
    input_per_mtok: float
    output_per_mtok: float


class ModelOut(ApiModel):
    id: str  # "provider:model", what a bot's modelId takes
    provider: str
    name: str
    context_window: int | None = None
    pricing: PricingOut | None = None


class ProviderProblem(ApiModel):
    provider: str
    message: str


class ModelListOut(ApiModel):
    """Models of every connected provider that answered; the ones that didn't are in `errors`."""

    models: list[ModelOut]
    errors: list[ProviderProblem]
