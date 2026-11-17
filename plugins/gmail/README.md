# botdesk-plugin-gmail

Gmail for BotDesk ([ADR 0011](../../docs/adr/0011-gmail-plugin.md)). Plugin id: `gmail`.

It connects a Google account and lets a bot search and read its email (slice 6.1), label, archive, draft, send and trash it (6.2), and react to new email (6.3). What the owner sets up and what bots can do: [the guide](../../docs/self-hosting/google-oauth.md); a manual test: [docs/testing/gmail.md](../../docs/testing/gmail.md).

## Connecting

`OAuth2Auth` with provider `google`, two access levels:

| Level | Scope | Read tools |
|---|---|---|
| `read` | `gmail.readonly` | yes |
| `full` (default) | `gmail.modify` | yes: `implied_scopes` says `gmail.modify` includes `gmail.readonly`; and the write tools |

The account is the mailbox's address from `users.getProfile`. It loads when `gmail` is in the API's `PLUGINS` setting, and Connect apps offers it once the server has a Google client (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`; see [the guide](../../docs/self-hosting/google-oauth.md)).

## Read tools

All `read`, idempotent, needing `gmail.readonly`, and `untrusted_output`: their results were written by people outside BotDesk, so reading them **taints the run** and every risky tool asks a person afterwards.

| Tool | Gmail API | Returns |
|---|---|---|
| `gmail.search(query, max_results=10)` (at most 25) | `messages.list` + `messages.get(format=metadata)` | id, threadId, from, to, subject, date, labels, snippet |
| `gmail.read_thread(thread_id)` | `threads.get(format=full)` | each message's kept headers, plain text and attachments (name, type, size) |
| `gmail.list_labels()` | `labels.list` | id, name, type |

How email reaches the model (`text.py`, ADR 0011 §4):

- **Headers:** only From, To, Cc, Date, Subject, Message-ID, In-Reply-To and References, each capped at 1 000 characters.
- **Body:** `text/plain` when the message has it; otherwise its HTML as text, without scripts, styles, hidden elements (`display:none`, `visibility:hidden`, zero size or opacity, `hidden`) or images, and with links as `text (url)`. Decoded with the part's charset.
- **Caps:** 20 000 characters per message and 60 000 per result. Newest messages get their text first; what is left out gets a `cut` note (`[cut: N more characters not shown]`), written outside the email block.
- **Delimiters:** email text (bodies and snippets) sits in `<email>` … `</email>` blocks. Any `<email>`, `</email>` or `<untrusted-content>` tag a sender writes is defused (its `<` becomes `‹`), so it can't end the block early. Every result also carries a `note` saying the content is data, not instructions.
- **Attachments** are listed, never downloaded.

Failures are readable and never quote Google's answer: 401 says to reconnect Gmail in Connect apps; 403, 404, 429 and 5xx each say what happened and what to do.

## Write tools

Need `gmail.modify`; one change per call, one request to Gmail, never retried by the tool (`write_tools.py`).

| Tool | Gmail API | Risk | Idempotent |
|---|---|---|---|
| `gmail.add_labels(thread_id, label_ids)` / `gmail.remove_labels(…)` | `threads.modify` | `write-external` | yes |
| `gmail.archive(thread_id)` (removes `INBOX`) | `threads.modify` | `write-external` | yes |
| `gmail.create_draft(to, cc, bcc, subject, body, reply_to_thread_id?)` | `drafts.create` | `write-external` | no |
| `gmail.send(…same…)` | `messages.send` | `external-send` | no |
| `gmail.trash(thread_id)` | `threads.trash` | `destructive` | yes |

- **Labels:** ids from `gmail.list_labels` (`STARRED`, `UNREAD`, `IMPORTANT`, `Label_12`…). `TRASH`, `SPAM`, `DRAFT` and `SENT` are refused: trashing is `gmail.trash`.
- **Mail:** plain text, built with the standard `email` package and sent as base64url `raw`; Gmail sets `From`. Recipients are bare addresses (no names, one per entry), at most 20 in To, Cc and Bcc together; the subject is one line; the body at most 50 000 characters. Anything that could add a header is refused by the args model, so it never reaches an approval card.
- **Replies:** `reply_to_thread_id` sends with `threadId`, and `In-Reply-To` / `References` from the thread's newest message (only well-formed message ids are copied). Use the thread's subject with `Re: ` so Gmail keeps the reply in the conversation.
- **Approval cards** get a one-line summary from the arguments alone: "Send an email to sara@acme.dev (cc omar@acme.dev; bcc boss@acme.dev): “Launch review”: Hi Sara, Thursday at 3 PM works. Ali" (the body's first 120 characters), "Add label STARRED to email thread 18f0a0", "Move email thread 18f0a0 to Trash".
- Sending an existing draft by id isn't offered: the card couldn't show what it contains.

## Trigger: `new_email`

`trigger.py`, polled every minute by BotDesk's `poll_triggers` job ([ADR 0011](../../docs/adr/0011-gmail-plugin.md) §5). The cursor is a Gmail `historyId`.

- **First poll** (no cursor): `users.getProfile` → its `historyId`. No events: old mail is never backfilled.
- **Then** `users.history.list(startHistoryId, historyTypes=messageAdded, labelId=INBOX, maxResults=500)`: each new inbox message is one event (`messages.get(format=metadata)` for From and Subject), oldest first, skipping `SENT` (your own mail, mail to yourself too), drafts, spam, trash, Promotions, Social and mail from the mailbox's own address. At most 10 per poll; a `notice` counts the rest.
- **Expired cursor** (404): back to the profile's current `historyId`, no events, and the notice "BotDesk missed some new mail…".
- **Events:** `summary` "New email from Sara Lee: Invoice 4471" (for the chat), `payload` `{messageId, threadId, from, subject, account}`. The run reads the mail itself with `gmail.read_thread`; trigger runs start tainted.

## Tests

```bash
cd plugins/gmail && uv run pytest -q
```

`tests/test_read_tools.py`, `test_write_tools.py` and `test_trigger.py` use `FakeHttp`. `tests/fixtures/` holds Gmail API answers (made up, shaped like the API reference): a plain thread, an HTML-only email, multipart with attachments, a Latin-1 body, and the **injection corpus** (instructions to forward everything, a delimiter break-out, hidden HTML, a tracking pixel). API-level tests (a connected mailbox, the tool pipeline, the policy for each write tool, taint, `GMAIL_API_BASE_URL`) are in `apps/api/tests/test_gmail_tools.py`; the trigger's routes and polling in `apps/api/tests/test_gmail_trigger.py`.
