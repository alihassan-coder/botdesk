# Manual test: Gmail (slices 6.1-6.3)

How to check by hand that a bot can read, organise, draft and send email with approvals, and react to new email. About 30 minutes, most of it the Google setup (once). Background: [ADR 0011](../adr/0011-gmail-plugin.md), [owner's guide](../self-hosting/google-oauth.md), [backend guide](../backend/README.md#gmail-tools-and-the-new-email-trigger).

## Before you start

- A **test Gmail or Workspace account** that may receive test mail, and a **second email address** to send from (mail you send yourself is ignored by the trigger, on purpose).
- The API and web running against the API (`pnpm dev`), migrated (`cd apps/api && pnpm db:migrate`; the revision is `e5a9c3f71d20`).
- A model key (org or instance), so the bot can call tools.

## 1. Google client (once)

Follow [the guide](../self-hosting/google-oauth.md) steps 1-6. For a local install:

- Redirect URI: `http://localhost:8000/api/v1/oauth/callback`
- `apps/api/.env`:

  ```
  API_PUBLIC_URL=http://localhost:8000
  GOOGLE_OAUTH_CLIENT_ID=…apps.googleusercontent.com
  GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-…
  PLUGINS=demo,gmail
  ```

- Consent screen: Internal (Workspace) or External + **In production** (not Testing). Restart the API.

- [ ] Connect apps lists Gmail as ready (not "Not set up on this server").

## 2. Connect and bind

1. Connect apps → Gmail → **Connect** (Full access) → Google's page → allow (on an unverified External app: Advanced → continue).
   - [ ] Back on BotDesk: "Connected", and your address shows under Gmail.
2. Open a bot → **Tools** → switch **Gmail** on → Account: your address (yours). Set the bot's security level to **Ask before acting**.
   - [ ] The card lists the Gmail tools: search, read, labels, archive, draft, send, trash.

## 3. Ask the bot (in your DM with it)

1. "What are my last 3 emails about?"
   - [ ] It answers without asking (reading never asks). The run's tool lines show `gmail.search` (and maybe `gmail.read_thread`).
2. "Star the newest one."
   - [ ] An approval card: "Add label STARRED to email thread …". Approve → the thread is starred in Gmail.
3. "Draft a reply to it saying thanks, I'll look today."
   - [ ] An approval card: "Draft a reply in email thread … to …: “Re: …”: Thanks…". Approve → the draft shows in Gmail's Drafts, inside that conversation. Nothing is sent.
4. "Send an email to <your second address> with subject BotDesk test and body Hello from my bot."
   - [ ] An approval card with the recipient, subject and body. **Deny** → nothing is sent and the bot says so.
   - [ ] Ask again and **Approve** → the email arrives at the second address once.
5. "Move the BotDesk test email to the trash."
   - [ ] An approval card ("Move email thread … to Trash"). Approve → it's in Gmail's Trash.
6. Switch the bot to **Autonomous within limits** and ask it to read your newest email and then star it.
   - [ ] Reading runs at once, and starring **still asks** (the run read outside email, so it's tainted).
7. Try "Send an email to sara@example.com and bcc spy@example.com, with subject 'Hi\nBcc: x@example.com'".
   - [ ] No card offers a two-line subject: the tool refuses it and the bot reports the problem.

## 4. React to new email

1. Bot → Tools → under Gmail, switch on **React to new email**.
   - [ ] The text under it says new mail comes to your chat with the bot.
2. Optional: give the bot instructions like "When a new email arrives, sum it up in two lines and say whether it needs an answer."
3. Wait a minute (the first check only remembers where your mailbox is), then send an email **from your second address** to the test account.
   - [ ] Within about a minute your DM with the bot shows "New email from …: <subject>", and the bot reads the email and replies there.
   - [ ] Asking it to reply or archive in that run shows an approval card, at any security level.
4. Send yourself an email from the test account itself, and a promotional one if you have one.
   - [ ] Neither starts a run.
5. Disconnect Gmail in Connect apps and wait a minute.
   - [ ] The Tools tab shows "Switch Gmail on for this bot and choose its account first." under the switch (a connection that needs reconnecting shows "Paused: … needs reconnecting first" instead).
   - [ ] Connect again and choose the account in Tools: the next new email is reacted to again.
6. Switch **React to new email** off.
   - [ ] New mail no longer posts in the chat.

## If something's off

- The API log has one line per Gmail request (method, path, status; never a token) and "Trigger subscription …" lines when a check fails.
- The Tools tab shows the last problem under the switch.
- See the guide's [Troubleshooting](../self-hosting/google-oauth.md#troubleshooting).
