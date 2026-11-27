from typing import Annotated

from fastapi import APIRouter, Form, UploadFile

from src.api.deps import AppSettings, Db, OrgAccess, Secrets, Voice
from src.controllers import voice_controller
from src.schemas.voice import TranscriptionOut, VoiceOut

router = APIRouter(prefix="/orgs/{org_id}/voice", tags=["voice"])


@router.get("")
async def voice_status(access: OrgAccess, db: Db, settings: AppSettings, secrets: Secrets, voice: Voice) -> VoiceOut:
    """Whether voice input works for you, and with which provider and model (your own key first)."""
    return await voice_controller.status(db, access, settings, secrets, voice)


@router.post("/transcriptions")
async def transcribe(
    audio: UploadFile,
    access: OrgAccess,
    db: Db,
    settings: AppSettings,
    secrets: Secrets,
    voice: Voice,
    hint: Annotated[str, Form()] = "",
) -> TranscriptionOut:
    """Write down a recording (at most 25 MB). `hint`: names in the chat, so they're spelled right.
    The audio is never stored."""
    return await voice_controller.transcribe(db, access, settings, secrets, voice, audio=audio, hint=hint)
