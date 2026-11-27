"""Voice input (ADR 0021): the composer records you and the API writes down what you said, with the
best speech-to-text model the member's keys reach (OpenAI's before Groq's; your own key first).
The audio is never stored."""

from typing import Any

import httpx
import pytest

from src.services import voice_service
from src.services.voice_service import speech_model
from tests.conftest import FakeProviders, sign_up
from tests.test_providers import GROQ_KEY, OPENAI_KEY

ORGS = "/api/v1/orgs"
AUDIO = b"\x1aE\xdf\xa3fake-webm-audio"


# Which model


def test_openai_prefers_a_full_transcribe_model_then_mini_then_whisper() -> None:
    ids = ["whisper-1", "gpt-4o-mini-transcribe", "gpt-4o-transcribe", "gpt-4o-transcribe-diarize", "gpt-5.5"]
    assert speech_model("openai", ids) == "gpt-4o-transcribe"
    assert speech_model("openai", ["whisper-1", "gpt-4o-mini-transcribe"]) == "gpt-4o-mini-transcribe"
    assert speech_model("openai", ["gpt-5.5", "whisper-1"]) == "whisper-1"


def test_openai_takes_a_newer_generation_and_the_alias_over_a_dated_snapshot() -> None:
    assert speech_model("openai", ["gpt-4o-transcribe", "gpt-5-transcribe"]) == "gpt-5-transcribe"
    assert speech_model("openai", ["gpt-4o-transcribe-2025-03-20", "gpt-4o-transcribe"]) == "gpt-4o-transcribe"


def test_openai_skips_realtime_preview_and_speech_out_models() -> None:
    ids = ["gpt-4o-realtime-preview", "gpt-4o-mini-tts", "gpt-4o-transcribe-diarize", "gpt-5.5"]
    assert speech_model("openai", ids) is None


def test_groq_prefers_whisper_large_v3_then_turbo_then_any_whisper() -> None:
    ids = ["whisper-large-v3-turbo", "llama-3.3-70b-versatile", "whisper-large-v3", "distil-whisper-large-v3-en"]
    assert speech_model("groq", ids) == "whisper-large-v3"
    assert speech_model("groq", ["whisper-large-v3-turbo", "distil-whisper-large-v3-en"]) == "whisper-large-v3-turbo"
    assert speech_model("groq", ["distil-whisper-large-v3-en"]) == "distil-whisper-large-v3-en"
    assert speech_model("groq", ["llama-3.3-70b-versatile"]) is None


def test_other_providers_have_no_speech_model() -> None:
    assert speech_model("anthropic", ["whisper-1"]) is None


# The API


def _models(ids: list[str]) -> dict[str, Any]:
    return {"data": [{"id": model, "object": "model", "active": True} for model in ids]}


class SpeechProvider:
    """A provider's /models and /audio/transcriptions. Records what each transcription was sent."""

    def __init__(self, key: str, models: list[str], *, text: str = " Hello BotDesk. ", status: int = 200) -> None:
        self.key, self.models, self.text, self.status = key, models, text, status
        self.sent: list[bytes] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {self.key}":
            return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=_models(self.models))
        assert request.url.path.endswith("/audio/transcriptions")
        self.sent.append(request.read())
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": f"upstream broke for key {self.key}"}})
        return httpx.Response(200, json={"text": self.text})


async def _org(client: httpx.AsyncClient) -> str:
    me = await sign_up(client)
    return f"{ORGS}/{me['organizations'][0]['id']}"


async def _connect(client: httpx.AsyncClient, path: str, provider: str, key: str) -> None:
    response = await client.put(f"{path}/providers/{provider}", json={"apiKey": key})
    assert response.status_code == 200, response.text


def _transcribe(client: httpx.AsyncClient, path: str, **form: str) -> Any:
    files = {"audio": ("voice.webm", AUDIO, "audio/webm;codecs=opus")}
    return client.post(f"{path}/voice/transcriptions", files=files, data=form)


async def test_without_a_speech_key_voice_is_off_and_says_how_to_turn_it_on(client: httpx.AsyncClient) -> None:
    path = await _org(client)
    status = (await client.get(f"{path}/voice")).json()
    assert status == {"available": False, "provider": None, "model": None, "message": voice_service.NO_VOICE}
    response = await _transcribe(client, path)
    assert response.status_code == 400
    assert response.json()["detail"] == voice_service.NO_VOICE


async def test_a_groq_key_turns_voice_on_with_whisper_large_v3(
    client: httpx.AsyncClient, providers: FakeProviders
) -> None:
    groq = SpeechProvider(GROQ_KEY, ["llama-3.3-70b-versatile", "whisper-large-v3-turbo", "whisper-large-v3"])
    providers.answer("api.groq.com", handler=groq)
    path = await _org(client)
    await _connect(client, path, "groq", GROQ_KEY)

    status = (await client.get(f"{path}/voice")).json()
    assert status == {"available": True, "provider": "Groq", "model": "whisper-large-v3", "message": None}

    response = await _transcribe(client, path, hint="Coder, Writer, BotDesk")
    assert response.status_code == 200, response.text
    assert response.json() == {"text": "Hello BotDesk.", "provider": "Groq", "model": "whisper-large-v3"}
    sent = groq.sent[0]
    assert AUDIO in sent  # the recording itself
    assert b'name="model"\r\n\r\nwhisper-large-v3\r\n' in sent
    assert b"Coder, Writer, BotDesk" in sent  # names, so they're spelled right


async def test_openai_comes_before_groq(client: httpx.AsyncClient, providers: FakeProviders) -> None:
    openai = SpeechProvider(OPENAI_KEY, ["gpt-5.5", "whisper-1", "gpt-4o-transcribe"], text="From OpenAI")
    groq = SpeechProvider(GROQ_KEY, ["whisper-large-v3"])
    providers.answer("api.openai.com", handler=openai)
    providers.answer("api.groq.com", handler=groq)
    path = await _org(client)
    await _connect(client, path, "groq", GROQ_KEY)
    await _connect(client, path, "openai", OPENAI_KEY)

    status = (await client.get(f"{path}/voice")).json()
    assert (status["provider"], status["model"]) == ("OpenAI", "gpt-4o-transcribe")
    assert (await _transcribe(client, path)).json()["text"] == "From OpenAI"
    assert groq.sent == []


async def test_a_provider_without_a_speech_model_is_passed_over(
    client: httpx.AsyncClient, providers: FakeProviders
) -> None:
    providers.answer("api.openai.com", handler=SpeechProvider(OPENAI_KEY, ["gpt-5.5"]))
    providers.answer("api.groq.com", handler=SpeechProvider(GROQ_KEY, ["whisper-large-v3-turbo"]))
    path = await _org(client)
    await _connect(client, path, "openai", OPENAI_KEY)
    await _connect(client, path, "groq", GROQ_KEY)
    status = (await client.get(f"{path}/voice")).json()
    assert (status["provider"], status["model"]) == ("Groq", "whisper-large-v3-turbo")


async def test_audio_that_isnt_audio_or_is_too_long_is_refused(
    client: httpx.AsyncClient, providers: FakeProviders, monkeypatch: pytest.MonkeyPatch
) -> None:
    groq = SpeechProvider(GROQ_KEY, ["whisper-large-v3"])
    providers.answer("api.groq.com", handler=groq)
    path = await _org(client)
    await _connect(client, path, "groq", GROQ_KEY)

    text = await client.post(f"{path}/voice/transcriptions", files={"audio": ("notes.txt", b"hi", "text/plain")})
    assert text.status_code == 400
    assert text.json()["detail"] == voice_service.NOT_AUDIO

    monkeypatch.setattr(voice_service, "MAX_AUDIO_BYTES", len(AUDIO) - 1)
    too_long = await _transcribe(client, path)
    assert too_long.status_code == 400
    assert too_long.json()["detail"] == voice_service.TOO_LONG
    assert groq.sent == []  # nothing reached the provider


async def test_a_provider_failure_says_so_without_the_key(client: httpx.AsyncClient, providers: FakeProviders) -> None:
    providers.answer("api.groq.com", handler=SpeechProvider(GROQ_KEY, ["whisper-large-v3"], status=500))
    path = await _org(client)
    await _connect(client, path, "groq", GROQ_KEY)
    response = await _transcribe(client, path)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail.startswith("Groq couldn't write down your voice")
    assert GROQ_KEY not in detail


async def test_the_model_list_is_cached(client: httpx.AsyncClient, providers: FakeProviders) -> None:
    providers.answer("api.groq.com", handler=SpeechProvider(GROQ_KEY, ["whisper-large-v3"]))
    path = await _org(client)
    await _connect(client, path, "groq", GROQ_KEY)
    before = providers.calls_to("api.groq.com")
    for _ in range(3):
        await client.get(f"{path}/voice")
    assert providers.calls_to("api.groq.com") == before + 1
