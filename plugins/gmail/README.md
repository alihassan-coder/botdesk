# botdesk-plugin-gmail

Gmail for BotDesk ([ADR 0011](../../docs/adr/0011-gmail-plugin.md)). Plugin id: `gmail`.

Today (slice 5.3) it only **connects** a Google account: it declares `OAuth2Auth` with provider `google`, two access levels (`read` = `gmail.readonly`, `full` = `gmail.modify`), and an `account` handler that reads the mailbox address from `users.getProfile`. It has no tools yet; reading and sending come in slices 6.1-6.3.

It loads when `gmail` is in the API's `PLUGINS` setting, and Connect apps offers it once the server has a Google client (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`; see [the guide](../../docs/self-hosting/google-oauth.md)).

```bash
cd plugins/gmail && uv run pytest -q
```
