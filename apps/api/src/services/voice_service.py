"""Voice input (ADR 0021): what you say, written down by the best speech-to-text model your keys reach.

OpenAI before Groq; each provider's key is found as a run's is (your own key, then the
organization's, then the server's). The model comes from the provider's live list (cached ten
minutes), so newer models are picked up by themselves. The audio passes through memory only: it
is never stored or logged.
"""

import hashlib
import re
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.errors import BadRequest, Unavailable
from src.core.secrets import SecretBox
from src.model_providers import ProviderError, scrub
from src.model_providers.base import get_json
from src.model_providers.openai_compatible import GROQ, OPENAI
from src.services import provider_service
from src.services.provider_service import ProviderAccess

# In order of quality. Both speak OpenAI's /audio/transcriptions.
SPEECH_PROVIDERS: dict[str, str] = {"openai": OPENAI.base_url or "", "groq": GROQ.base_url or ""}
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # the providers' own limit
MAX_HINT_CHARS = 300
CACHE_SECONDS = 600.0
TRANSCRIBE_TIMEOUT = 120.0
AUDIO_TYPES = frozenset(
    {
        "audio/webm",
        "video/webm",  # some browsers label a recording without video this way
        "audio/ogg",
        "audio/mp4",
        "audio/m4a",
        "audio/x-m4a",
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/flac",
    }
)

NO_VOICE = "Voice needs an OpenAI or Groq key. Add one in Settings → Models & keys."
NOT_AUDIO = "That isn't a recording we can read. Try again."
TOO_LONG = "That recording is too long. Keep it under 10 minutes."
EMPTY = "That recording is empty. Try again."

_SKIP_OPENAI = ("diarize", "realtime", "preview", "tts", "search", "audio")
_VERSION = re.compile(r"(\d+(?:\.\d+)?)")


def _version(model: str) -> float:
    """The first number in a model's id ("gpt-4o-transcribe" → 4, "whisper-large-v3" → 3): bigger is newer."""
    found = _VERSION.search(model)
    return float(found.group(1)) if found else 0.0


def _openai_tier(model: str) -> int | None:
    if any(word in model for word in _SKIP_OPENAI):
        return None
    if "transcribe" in model:
        return 1 if "mini" in model else 0
    return 2 if model.startswith("whisper") else None


def _groq_tier(model: str) -> int | None:
    if "whisper" not in model:
        return None
    if model.startswith("whisper-large"):
        return 1 if "turbo" in model else 0
    return 2


_TIERS: dict[str, Callable[[str], int | None]] = {"openai": _openai_tier, "groq": _groq_tier}


def speech_model(provider_kind: str, model_ids: Iterable[str]) -> str | None:
    """The best speech-to-text model in a provider's list, or None. Best: the better tier, then the
    newer generation, then the plain alias over a dated snapshot ("gpt-4o-transcribe" before
    "gpt-4o-transcribe-2025-03-20")."""
    tier_of = _TIERS.get(provider_kind)
    if tier_of is None:
        return None
    ranked = [
        (tier, -_version(model), len(model), model)
        for model in {model.strip().lower() for model in model_ids if model}
        if (tier := tier_of(model)) is not None
    ]
    return min(ranked)[3] if ranked else None


@dataclass(frozen=True)
class SpeechTarget:
    access: ProviderAccess
    model: str

    @property
    def provider_name(self) -> str:
        return self.access.name


def _audio_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def check_audio(data: bytes, content_type: str | None) -> None:
    """Refuses what isn't a recording, is empty, or is over the size limit, before any provider sees it."""
    if _audio_type(content_type) not in AUDIO_TYPES:
        raise BadRequest(NOT_AUDIO)
    if not data:
        raise BadRequest(EMPTY)
    if len(data) > MAX_AUDIO_BYTES:
        raise BadRequest(TOO_LONG)


class SpeechToText:
    """Finds the speech model and calls it. One per app (`app.state.voice`); caches each key's choice."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        ttl_seconds: float = CACHE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.http = http
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._chosen: dict[tuple[uuid.UUID, str, str], tuple[float, str | None]] = {}

    async def target(
        self,
        db: AsyncSession,
        org_id: uuid.UUID,
        settings: Settings,
        secrets: SecretBox,
        *,
        member_id: uuid.UUID,
    ) -> SpeechTarget | None:
        """The first speech provider (in quality order) whose key reaches a speech model. A key that
        can't be read, or a provider that's down, is passed over."""
        for kind in SPEECH_PROVIDERS:
            try:
                access = await provider_service.connection_for(
                    db, org_id, kind, settings, secrets, requester_id=member_id
                )
                model = await self._model(org_id, access) if access else None
            except ProviderError:
                continue
            if access and model:
                return SpeechTarget(access, model)
        return None

    async def _model(self, org_id: uuid.UUID, access: ProviderAccess) -> str | None:
        key = (org_id, access.provider_id, hashlib.sha256(access.api_key.encode()).hexdigest())
        cached = self._chosen.get(key)
        if cached and cached[0] > self.clock():
            return cached[1]
        headers = {"Authorization": f"Bearer {access.api_key}"}
        body: Any = await get_json(
            self.http, f"{SPEECH_PROVIDERS[access.kind]}/models", api_key=access.api_key, headers=headers
        )
        rows = body.get("data", []) if isinstance(body, dict) else body if isinstance(body, list) else []
        ids = [
            str(row["id"]) for row in rows if isinstance(row, dict) and row.get("id") and row.get("active") is not False
        ]
        model = speech_model(access.kind, ids)
        self._chosen[key] = (self.clock() + self.ttl_seconds, model)
        return model

    async def transcribe(
        self, target: SpeechTarget, data: bytes, *, filename: str, content_type: str | None, hint: str = ""
    ) -> str:
        """What was said. Raises `Unavailable` with the provider's reason (the key taken out)."""
        api_key = target.access.api_key
        form = {"model": target.model, "response_format": "json"}
        if hint := " ".join(hint.split())[:MAX_HINT_CHARS]:
            form["prompt"] = hint
        failed = f"{target.provider_name} couldn't write down your voice"
        try:
            response = await self.http.post(
                f"{SPEECH_PROVIDERS[target.access.kind]}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data=form,
                files={"file": (filename or "voice.webm", data, _audio_type(content_type))},
                timeout=TRANSCRIBE_TIMEOUT,
            )
        except httpx.TimeoutException as error:
            raise Unavailable(f"{failed}: it didn't answer in time.") from error
        except httpx.HTTPError as error:
            raise Unavailable(f"{failed}: we couldn't reach it ({type(error).__name__}).") from error
        if response.status_code >= 400:
            raise Unavailable(f"{failed}: {response.status_code}: {scrub(_error_text(response), api_key)}")
        try:
            body = response.json()
        except ValueError as error:
            raise Unavailable(f"{failed}: it didn't answer with JSON.") from error
        text = body.get("text") if isinstance(body, dict) else None
        return " ".join(str(text or "").split())


def _error_text(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        return response.text or response.reason_phrase
    error = body.get("error", body) if isinstance(body, dict) else body
    if isinstance(error, dict):
        return str(error.get("message") or response.reason_phrase)
    return str(error)
