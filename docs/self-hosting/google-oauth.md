# Set up Google sign-in (Gmail) for your BotDesk server

BotDesk has no hosted service, so each server uses its own Google OAuth client ([ADR 0011](../adr/0011-gmail-plugin.md) §6). Until it is set, Connect apps shows Google apps as "Not set up on this server".

1. **Create a Google Cloud project** at https://console.cloud.google.com and enable the **Gmail API** (APIs & Services → Library).
2. **Consent screen** (Google Auth Platform → Branding / Audience):
   - **Google Workspace:** choose **Internal**. Only your domain's users can connect, there is no verification and no "unverified app" screen. Recommended.
   - **Personal Gmail or outside accounts:** choose **External**, then **Publish app → In production**. Never stay in **Testing**: Google's refresh tokens then expire after **7 days**, and every connection breaks weekly (it shows as "Needs reconnect"). In production but unverified, people see Google's "unverified app" screen once (Advanced → continue); the cap of 100 users is plenty for one team.
3. **Scopes** (Data access): add `https://www.googleapis.com/auth/gmail.readonly` and `https://www.googleapis.com/auth/gmail.modify`. Nothing else (never `https://mail.google.com/` or `gmail.settings.*`).
4. **Client** (Clients → Create client): type **Web application**, with the authorized redirect URI
   `{API_PUBLIC_URL}/api/v1/oauth/callback` — for example `https://api.botdesk.example.com/api/v1/oauth/callback`, or `http://localhost:8000/api/v1/oauth/callback` on your own machine. Google needs HTTPS and a host name (no raw IP) except for `localhost`, so a LAN install needs a real HTTPS name behind a reverse proxy.
5. **Environment** (`apps/api/.env`, or `deploy/.env` with Docker), then restart the API:

   ```
   API_PUBLIC_URL=https://api.botdesk.example.com
   GOOGLE_OAUTH_CLIENT_ID=1234-abc.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-...
   ```

   `API_PUBLIC_URL` must match the redirect URI exactly. Keep the secret out of version control.

6. **Load the plugin:** `PLUGINS` must include `gmail` (for example `PLUGINS=demo,gmail`, as in `.env.example`). Restart the API; Connect apps now offers Gmail with **Read** or **Full** access (Full is the default).

## Troubleshooting

After Google's page, BotDesk shows a result page (`/apps/callback`). Its error codes:

- **denied:** you cancelled on Google's page.
- **expired:** the sign-in took more than 10 minutes, was already used, or was started in another account's session. Start again from Connect apps.
- **not-configured:** the Google client was removed from the server while you were signing in.
- **signed-out / forbidden:** sign in to BotDesk first; or you lost the role needed for that owner (an organization account needs an owner or admin).
- **failed:** the code exchange or the account lookup failed. The API log says which (never with a token in it).

Other problems:

- **`redirect_uri_mismatch`** on Google's page: the URI in step 4 and `API_PUBLIC_URL` differ (scheme, host, port or trailing path).
- **A connection says "Needs reconnect" about a week after connecting:** the consent screen is still in Testing (step 2).
- **"Access blocked: app not verified"** with no Advanced link: the account is outside your Workspace and the app is Internal; use External + In production.
