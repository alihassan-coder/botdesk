"""Voice input (ADR 0021)."""

from src.schemas.common import ApiModel


class VoiceOut(ApiModel):
    """Whether the composer's microphone works, and with which provider and model. `message` says
    how to turn it on when it doesn't."""

    available: bool
    provider: str | None
    model: str | None
    message: str | None


class TranscriptionOut(ApiModel):
    text: str
    provider: str
    model: str
