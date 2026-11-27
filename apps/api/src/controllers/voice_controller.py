"""Voice input (ADR 0021): any member, with the best speech model their keys reach."""

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import Access
from src.core.config import Settings
from src.core.errors import BadRequest
from src.core.secrets import SecretBox
from src.schemas.voice import TranscriptionOut, VoiceOut
from src.services import voice_service
from src.services.voice_service import SpeechToText


async def status(
    db: AsyncSession, access: Access, settings: Settings, secrets: SecretBox, voice: SpeechToText
) -> VoiceOut:
    target = await voice.target(db, access.org.id, settings, secrets, member_id=access.user.id)
    if target is None:
        return VoiceOut(available=False, provider=None, model=None, message=voice_service.NO_VOICE)
    return VoiceOut(available=True, provider=target.provider_name, model=target.model, message=None)


async def transcribe(
    db: AsyncSession,
    access: Access,
    settings: Settings,
    secrets: SecretBox,
    voice: SpeechToText,
    *,
    audio: UploadFile,
    hint: str,
) -> TranscriptionOut:
    # One byte over the limit is enough to refuse it; never read more than that.
    data = await audio.read(voice_service.MAX_AUDIO_BYTES + 1)
    voice_service.check_audio(data, audio.content_type)
    target = await voice.target(db, access.org.id, settings, secrets, member_id=access.user.id)
    if target is None:
        raise BadRequest(voice_service.NO_VOICE)
    # Nothing is written to the database: the session only read the keys. Close it before the
    # provider call, which can take seconds.
    await db.close()
    text = await voice.transcribe(
        target, data, filename=audio.filename or "", content_type=audio.content_type, hint=hint
    )
    return TranscriptionOut(text=text, provider=target.provider_name, model=target.model)
