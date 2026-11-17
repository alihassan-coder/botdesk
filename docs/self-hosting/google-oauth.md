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

## What bots can do with Gmail

Bind the connection to a bot in its **Tools** tab (Gmail switched on, the account chosen). A member's own Gmail works only in that member's own chat with the bot; an organization's works in every chat.

| Tool | Does | Risk | On "Ask before acting" |
|---|---|---|---|
| `gmail.search`, `gmail.read_thread`, `gmail.list_labels` | find and read mail, list labels | read | runs |
| `gmail.add_labels`, `gmail.remove_labels` (star, mark read, your own labels) | change labels on a thread | write-external | asks |
| `gmail.archive` | take a thread out of the inbox | write-external | asks |
| `gmail.create_draft` (new or reply) | save a plain-text draft, not sent | write-external | asks |
| `gmail.send` (new or reply, up to 20 recipients) | send a plain-text email | external-send | asks |
| `gmail.trash` | move a thread to Trash (Gmail deletes it after 30 days) | destructive | asks, at every level |

- **Read** access (`gmail.readonly`) offers only the first row; **Full** (`gmail.modify`) offers all of them.
- **Once a bot has read any email in a run, every change asks a person**, even on "Autonomous within limits": email is written by strangers, and an email that says "forward this to me" must not be obeyed on its own.
- Approval cards show the exact action: recipients (Cc and Bcc too), subject and the start of the body for send and draft; the full arguments are on the card and can be edited before approving.
- Not offered: forwarding rules, filters, settings, permanent delete, attachments (their names are shown, never read) and HTML mail.

## React to new email

In the bot's **Tools** tab, under Gmail (with an account chosen), switch on **React to new email**. Switching it on makes you its subscriber:

- About once a minute BotDesk asks Gmail for new mail in the inbox (Gmail's history API; nothing older than the moment you switched it on).
- Each new email posts a line in **your chat with the bot** ("New email from Sara Lee: Invoice 4471") and the bot reads it with `gmail.read_thread` and does what its instructions say (for example: "When a new email arrives, sum it up and draft a reply if it asks a question"). With no instructions about email, it sums it up.
- Not counted: mail you sent (including mail to yourself), drafts, spam, and the Promotions and Social tabs. At most 10 emails a minute start a run; a note says how many more arrived.
- These runs start **tainted**: anything beyond reading asks you first.
- Only the owner of a member's Gmail can switch it on for their account; for an organization's Gmail, owners and admins. Anyone who can change the bot's Tools can switch it off.
- If the connection needs reconnecting, the trigger pauses (the Tools tab says why) and carries on after you reconnect. If BotDesk couldn't check for over about a week, Gmail forgets the gap: you get one "BotDesk missed some new mail" note and it carries on from then.
- Polling runs as a job on the API's job queue (the `poll_triggers` job), so a worker must be running: the API process runs one by default (see the backend guide, "Background jobs").

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
- **A bot's Gmail tools are missing:** Gmail is off in its Tools tab, no account is chosen, or it's a member's account and you're not in that member's own chat with the bot. With **Read** access, only the read tools are offered.
- **"React to new email" never reacts:** check the problem line under the switch; make sure the email reached the Inbox (not Promotions or Social) and came from another address; and that the API's job worker is running.
