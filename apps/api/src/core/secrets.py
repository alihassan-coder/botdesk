"""Encrypting secrets at rest (organizations' model provider keys).

Fernet (AES-128-CBC + HMAC-SHA256) from `cryptography`. Its key is derived from SECRET_KEY with
HKDF, so SECRET_KEY can be any long random string and other features can later derive their own
keys from it without sharing one.

Production refuses to start without SECRET_KEY. In development a fixed key keeps saved keys
readable across restarts; it is public (it's in this file), so it only suits throwaway data.
"""

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.core.config import Settings

log = logging.getLogger(__name__)

DEVELOPMENT_SECRET = "botdesk-development-only-secret-do-not-use-in-production"  # noqa: S105
KEY_PURPOSE = b"botdesk:provider-keys:v1"


class SecretUnreadable(Exception):
    """A saved secret can't be decrypted: SECRET_KEY changed since it was saved, or it was tampered with."""


class SecretBox:
    def __init__(self, secret: str) -> None:
        derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=KEY_PURPOSE).derive(secret.encode())
        self._fernet = Fernet(base64.urlsafe_b64encode(derived))

    def __repr__(self) -> str:
        return "SecretBox(<hidden>)"

    def encrypt(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as error:
            raise SecretUnreadable("This secret can't be decrypted with the current SECRET_KEY.") from error


def build_secret_box(settings: Settings) -> SecretBox:
    """The app's SecretBox. Called while the app is created, so production fails fast without a key."""
    secret = settings.secret_key.get_secret_value() if settings.secret_key else ""
    if secret:
        return SecretBox(secret)
    if settings.is_production:
        raise RuntimeError(
            "SECRET_KEY is not set. It encrypts saved API keys and is required in production. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    if settings.environment == "development":
        log.warning("SECRET_KEY isn't set: saved API keys use a development key. Set SECRET_KEY before real use.")
    return SecretBox(DEVELOPMENT_SECRET)
