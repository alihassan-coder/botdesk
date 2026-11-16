"""GMAIL PLUGIN (`botdesk-plugin-gmail`, plugin id `gmail`), ADR 0011.

Slice 5.3: it connects a Google account and shows which mailbox it is. No tools yet (slice 6.1).

- `OAuth2Auth` with provider `google`: BotDesk's one OAuth flow signs people in with the server's
  own Google client (`GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`).
- Two access levels: `read` (`gmail.readonly`) and `full` (`gmail.modify`, the default). Never
  `https://mail.google.com/` or the settings scopes.
- `access_type=offline` and `prompt=consent`, so Google sends a refresh token on every sign-in,
  reconnects included.
- The account is the mailbox's address from `users.getProfile`, compared in lower case.
"""

from botdesk_plugin_sdk import AccountIdentity, HttpClient, OAuth2Auth, PluginManifest

GMAIL_HOST = "gmail.googleapis.com"
GMAIL_API = f"https://{GMAIL_HOST}"

READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"


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
)


def gmail_plugin() -> PluginManifest:
    """The entry point."""
    return PluginManifest(
        id="gmail",
        name="Gmail",
        version="0.1.0",
        description="Connect a Gmail account. Tools that read and send its email come in a later release.",
        tools=(),
        auth=GOOGLE,
        egress=(GMAIL_HOST,),
    )
