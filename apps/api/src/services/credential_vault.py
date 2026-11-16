"""The credential vault: the only code that encrypts or decrypts a connection's credential (ADR 0010 §6).

    vault.save(connection, api_key_secret("lin_api_…", ApiKeyAuth()))  # encrypt into the row
    credential = vault.open(connection)                                # only inside a tool call
    vault.save(connection, oauth_secret(access, refresh))              # OAuth: tokens (services/oauth_flow.py)
    vault.revoke(connection, reason="Disconnected by Ali")             # null it, for good

It works on `Connection` rows and never touches the database itself: the caller commits.
Credentials use their own key (`SecretBox` with the `botdesk:connections:v1` purpose), so a model
key's ciphertext can't be pasted into a connection row and decrypt there. `SECRET_KEY` rotation
works as for model keys: a credential saved under `SECRET_KEY_OLD` still opens, and the next save
encrypts it with the new key.

A `Credential` never prints its secret and gives it out only as the request headers that carry
it, which only the authorised HTTP client (`plugins/authorised_http.py`) asks for.
"""

import json
from collections.abc import Mapping
from typing import Any

from botdesk_plugin_sdk import ApiKeyAuth
from pydantic import SecretStr

from src.core.config import Settings
from src.core.secrets import CONNECTIONS_PURPOSE, SecretBox, SecretUnreadable, build_secret_box
from src.models import Connection


class CredentialUnavailable(Exception):
    """The connection can't be used: disconnected, needs reconnecting, or its secret can't be
    read (SECRET_KEY changed). The message is safe to show people."""


class Credential:
    """A decrypted credential, for one tool call. Its repr and str hide the secret."""

    __slots__ = ("_bundle",)

    def __init__(self, bundle: Mapping[str, Any]) -> None:
        self._bundle = dict(bundle)

    def __repr__(self) -> str:
        return f"Credential({self._bundle.get('kind', '?')}, <hidden>)"

    __str__ = __repr__

    def auth_headers(self) -> dict[str, str]:
        """The headers that authorise a request: `{header: prefix + key}` for an API key,
        `Authorization: Bearer <access token>` for OAuth."""
        if self._bundle.get("kind") == "api_key":
            return {str(self._bundle["header"]): f"{self._bundle.get('prefix', '')}{self._bundle['api_key']}"}
        token_type = str(self._bundle.get("token_type") or "Bearer")
        return {"Authorization": f"{token_type.capitalize()} {self._bundle['access_token']}"}


def api_key_secret(api_key: str, auth: ApiKeyAuth) -> dict[str, str]:
    """The bundle an API-key connection saves: the key and how it's sent."""
    return {"kind": "api_key", "api_key": api_key, "header": auth.header, "prefix": auth.prefix}


def oauth_secret(access_token: str, refresh_token: str | None, token_type: str = "Bearer") -> dict[str, str]:  # noqa: S107
    """The bundle an OAuth connection saves: its tokens. No refresh token: the access token only
    lasts until it expires (then the connection needs reconnecting)."""
    bundle = {"kind": "oauth2", "access_token": access_token, "token_type": token_type or "Bearer"}
    if refresh_token:
        bundle["refresh_token"] = refresh_token
    return bundle


class CredentialVault:
    def __init__(self, box: SecretBox) -> None:
        self._box = box

    @classmethod
    def from_settings(cls, settings: Settings) -> "CredentialVault":
        return cls(build_secret_box(settings, purpose=CONNECTIONS_PURPOSE))

    def __repr__(self) -> str:
        return "CredentialVault(<hidden>)"

    def save(self, connection: Connection, secret: Mapping[str, Any]) -> None:
        """Encrypt `secret` into the row (with the current SECRET_KEY) and mark it active."""
        connection.encrypted_secret = self._box.encrypt(json.dumps(dict(secret), separators=(",", ":")))
        connection.status = "active"
        connection.status_reason = None

    def open(self, connection: Connection) -> Credential:
        """The credential, for a request about to be made. Refuses a connection that isn't active."""
        if connection.status != "active" or not connection.encrypted_secret:
            raise CredentialUnavailable(_unusable(connection))
        try:
            return Credential(json.loads(self._box.decrypt(connection.encrypted_secret)))
        except (SecretUnreadable, ValueError) as error:
            raise CredentialUnavailable(
                f"{connection.account_label}'s saved credential can't be read (did SECRET_KEY change?). "
                "Reconnect it in Connect apps."
            ) from error

    def refresh_token(self, connection: Connection) -> SecretStr | None:
        """An OAuth connection's refresh token, for the token endpoint (the OAuth module only).
        None when it has none or it can't be read."""
        return _token(self._bundle(connection), "refresh_token")

    def revocation_token(self, connection: Connection) -> SecretStr | None:
        """What to revoke at the provider on disconnect: the refresh token (which takes its access
        tokens with it), else the access token. None for API keys, which have nothing to revoke."""
        bundle = self._bundle(connection)
        if bundle.get("kind") != "oauth2":
            return None
        return _token(bundle, "refresh_token") or _token(bundle, "access_token")

    def seal(self, value: str) -> str:
        """Encrypt a short-lived secret that isn't a credential (an OAuth flow's PKCE verifier)."""
        return self._box.encrypt(value)

    def unseal(self, sealed: str) -> str:
        """`seal`, undone. Raises `SecretUnreadable` if SECRET_KEY changed in between."""
        return self._box.decrypt(sealed)

    def _bundle(self, connection: Connection) -> dict[str, Any]:
        if not connection.encrypted_secret:
            return {}
        try:
            bundle = json.loads(self._box.decrypt(connection.encrypted_secret))
        except (SecretUnreadable, ValueError):
            return {}
        return bundle if isinstance(bundle, dict) else {}

    def revoke(self, connection: Connection, *, reason: str) -> None:
        """Forget the credential for good. The row stays, `revoked`, for the audit trail."""
        connection.encrypted_secret = None
        connection.status = "revoked"
        connection.status_reason = reason
        connection.refresh_lease_until = None


def _token(bundle: Mapping[str, Any], key: str) -> SecretStr | None:
    value = bundle.get(key)
    return SecretStr(value) if isinstance(value, str) and value else None


def _unusable(connection: Connection) -> str:
    if connection.status == "needs_reconnect":
        return f"{connection.account_label} needs reconnecting (Connect apps)."
    return f"{connection.account_label} was disconnected. Connect it again in Connect apps."
