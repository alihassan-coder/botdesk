"""GMAIL PLUGIN (`botdesk-plugin-gmail`, plugin id `gmail`), ADR 0011.

- `OAuth2Auth` with provider `google`: BotDesk's one OAuth flow signs people in with the server's
  own Google client (`GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`).
- Two access levels: `read` (`gmail.readonly`) and `full` (`gmail.modify`, the default). Never
  `https://mail.google.com/` or the settings scopes. `gmail.modify` implies `gmail.readonly`,
  so a full-access connection gets the read tools too.
- `access_type=offline` and `prompt=consent`, so Google sends a refresh token on every sign-in,
  reconnects included.
- The account is the mailbox's address from `users.getProfile`, compared in lower case.
- Slice 6.1: the read tools `search`, `read_thread` and `list_labels` (`tools.py`). Their results
  taint the run; email text is plain, capped and inside `<email>` blocks (`text.py`).
- Slice 6.2: the write tools `add_labels`, `remove_labels`, `archive`, `create_draft`, `send` and
  `trash` (`write_tools.py`), all needing `gmail.modify`.
- Slice 6.3: the `new_email` trigger (`trigger.py`), polled every minute by BotDesk's job queue.
"""

from botdesk_plugin_sdk import AccountIdentity, HttpClient, OAuth2Auth, PluginManifest

from botdesk_gmail.api import GMAIL_API, GMAIL_HOST, GmailError
from botdesk_gmail.tools import READ_SCOPE, TOOLS
from botdesk_gmail.trigger import NEW_EMAIL
from botdesk_gmail.write_tools import MODIFY_SCOPE, WRITE_TOOLS

__all__ = ["GMAIL_API", "GMAIL_HOST", "GOOGLE", "MODIFY_SCOPE", "READ_SCOPE", "GmailError", "gmail_plugin"]


async def gmail_account(http: HttpClient) -> AccountIdentity:
    """Who signed in: the mailbox's address (`users.getProfile`)."""
    response = await http.request("GET", f"{GMAIL_API}/gmail/v1/users/me/profile")
    email = response.json().get("emailAddress") if response.ok else None
    if not isinstance(email, str) or not email.strip():
        raise ValueError(f"Gmail didn't say which mailbox this is (status {response.status_code}).")
    return AccountIdentity(label=email.strip(), ref=email.strip().casefold())


GOOGLE = OAuth2Auth(
    provider="google",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",  # noqa: S106  (an address, not a secret)
    revoke_url="https://oauth2.googleapis.com/revoke",
    scope_sets={"read": (READ_SCOPE,), "full": (MODIFY_SCOPE,)},
    extra_authorize_params={"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"},
    account=gmail_account,
    # Google: gmail.modify allows "all read/write operations except immediate, permanent
    # deletion", so it covers everything gmail.readonly does.
    implied_scopes={MODIFY_SCOPE: (READ_SCOPE,)},
)


def gmail_plugin() -> PluginManifest:
    """The entry point."""
    return PluginManifest(
        id="gmail",
        name="Gmail",
        version="0.1.0",
        description="Search, read, label, archive, draft, send and trash email in a connected Gmail account.",
        tools=TOOLS + WRITE_TOOLS,
        auth=GOOGLE,
        egress=(GMAIL_HOST,),
        triggers=(NEW_EMAIL,),
    )
