"""The Gmail plugin through the SDK's test helpers: no app, no database, no network."""

from importlib.metadata import entry_points

import pytest
from botdesk_plugin_sdk import ENTRY_POINT_GROUP, OAuth2Auth, validate_manifest
from botdesk_plugin_sdk.testing import FakeHttp

from botdesk_gmail import GMAIL_API, gmail_plugin

PROFILE = f"{GMAIL_API}/gmail/v1/users/me/profile"


def _auth() -> OAuth2Auth:
    auth = gmail_plugin().auth
    assert isinstance(auth, OAuth2Auth)
    return auth


def test_the_manifest_is_valid() -> None:
    manifest = validate_manifest(gmail_plugin())
    assert manifest.id == "gmail"
    assert manifest.egress == ("gmail.googleapis.com",)


def test_it_is_registered_under_the_botdesk_entry_point() -> None:
    (entry,) = [ep for ep in entry_points(group=ENTRY_POINT_GROUP) if ep.name == "gmail"]
    assert entry.load() is gmail_plugin


def test_it_signs_in_with_google_and_offers_read_and_full_access() -> None:
    auth = _auth()
    assert auth.provider == "google"
    assert auth.scope_sets == {
        "read": ("https://www.googleapis.com/auth/gmail.readonly",),
        "full": ("https://www.googleapis.com/auth/gmail.modify",),
    }
    assert auth.authorize_url == "https://accounts.google.com/o/oauth2/v2/auth"
    assert auth.token_url == "https://oauth2.googleapis.com/token"  # noqa: S105  (an address)
    assert auth.revoke_url == "https://oauth2.googleapis.com/revoke"
    # A refresh token every time, and consent shown again so Google sends it on a reconnect too.
    assert dict(auth.extra_authorize_params) == {
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }


async def test_the_account_is_the_mailbox_email_address() -> None:
    http = FakeHttp(gmail_plugin())
    http.route("GET", PROFILE, json={"emailAddress": "Ali@Acme.dev", "messagesTotal": 3})
    auth = _auth()
    assert auth.account is not None
    identity = await auth.account(http)
    assert identity.label == "Ali@Acme.dev"
    assert identity.ref == "ali@acme.dev"  # the same mailbox however Google spells it


async def test_a_profile_without_an_address_is_an_error() -> None:
    http = FakeHttp(gmail_plugin())
    http.route("GET", PROFILE, status=401, json={"error": {"code": 401}})
    auth = _auth()
    assert auth.account is not None
    with pytest.raises(ValueError, match="Gmail"):
        await auth.account(http)
