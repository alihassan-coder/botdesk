"""Encrypting secrets at rest (organizations' model provider keys).

Fernet (AES-128-CBC + HMAC-SHA256) from `cryptography`. Its key is derived from SECRET_KEY with
HKDF, so SECRET_KEY can be any long random string and other features can later derive their own
keys from it without sharing one.

Rules, so a misconfigured server fails closed instead of quietly using a weak key:

- SECRET_KEY must be at least 32 characters, and the API refuses to start without one, unless
  ENVIRONMENT is explicitly development or test. Those fall back to a fixed development key,
  which is public (it's in this file), so it only suits throwaway data.
- Rotation: set the new SECRET_KEY and move the old one to SECRET_KEY_OLD (comma-separated for
  several). Everything is encrypted with SECRET_KEY; keys saved under an old one still decrypt
  (MultiFernet tries each), and are encrypted with the new one the next time they're saved.
"""

import base64
import logging
from collections.abc import Sequence

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.core.config import Settings

log = logging.getLogger(__name__)

DEVELOPMENT_SECRET = "botdesk-development-only-secret-do-not-use-in-production"  # noqa: S105
KEY_PURPOSE = b"botdesk:provider-keys:v1"
MIN_SECRET_LENGTH = 32
GENERATE_HINT = 'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'


class SecretUnreadable(Exception):
    """A saved secret can't be decrypted: SECRET_KEY changed since it was saved, or it was tampered with."""


def _fernet(secret: str) -> Fernet:
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=KEY_PURPOSE).derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


class SecretBox:
    """Encrypts with `secret`; decrypts with `secret` or any of `old_secrets` (key rotation)."""

    def __init__(self, secret: str, old_secrets: Sequence[str] = ()) -> None:
        self._fernet = MultiFernet([_fernet(secret), *(_fernet(old) for old in old_secrets)])

    def __repr__(self) -> str:
        return "SecretBox(<hidden>)"

    def encrypt(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as error:
            raise SecretUnreadable("This secret can't be decrypted with the current SECRET_KEY.") from error


def _old_secrets(settings: Settings) -> list[str]:
    raw = settings.secret_key_old.get_secret_value() if settings.secret_key_old else ""
    return [old.strip() for old in raw.split(",") if old.strip()]


def build_secret_box(settings: Settings) -> SecretBox:
    """The app's SecretBox. Called while the app is created, so a server without a proper
    SECRET_KEY stops at startup with a message that says what to do."""
    secret = settings.secret_key.get_secret_value() if settings.secret_key else ""
    old = _old_secrets(settings)
    if not settings.relaxed_secrets:
        if not secret:
            raise RuntimeError(
                "SECRET_KEY is not set. It encrypts saved API keys and is required unless "
                f"ENVIRONMENT is development or test. {GENERATE_HINT}"
            )
        if len(secret) < MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"SECRET_KEY is too short ({len(secret)} characters); use at least {MIN_SECRET_LENGTH} random "
                f"characters. {GENERATE_HINT}. To keep saved keys readable, move the current one to SECRET_KEY_OLD."
            )
    if secret:
        return SecretBox(secret, old)
    log.warning("SECRET_KEY isn't set: saved API keys use a public development key. Set SECRET_KEY before real use.")
    return SecretBox(DEVELOPMENT_SECRET, old)
