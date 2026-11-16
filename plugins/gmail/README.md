# botdesk-plugin-gmail

Gmail for BotDesk ([ADR 0011](../../docs/adr/0011-gmail-plugin.md)). Plugin id: `gmail`.

It connects a Google account and lets a bot search and read its email (slice 6.1). Labelling, drafts and sending come in slice 6.2; the new-email trigger in 6.3.

## Connecting

`OAuth2Auth` with provider `google`, two access levels:

| Level | Scope | Read tools |
|---|---|---|
| `read` | `gmail.readonly` | yes |
| `full` (default) | `gmail.modify` | yes: `implied_scopes` says `gmail.modify` includes `gmail.readonly` |

The account is the mailbox's address from `users.getProfile`. It loads when `gmail` is in the API's `PLUGINS` setting, and Connect apps offers it once the server has a Google client (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`; see [the guide](../../docs/self-hosting/google-oauth.md)).

## Tools

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

## Tests

```bash
cd plugins/gmail && uv run pytest -q
```

`tests/fixtures/` holds Gmail API answers (made up, shaped like the API reference): a plain thread, an HTML-only email, multipart with attachments, a Latin-1 body, and the **injection corpus** (instructions to forward everything, a delimiter break-out, hidden HTML, a tracking pixel). API-level tests (a connected mailbox, the tool pipeline, taint, `GMAIL_API_BASE_URL`) are in `apps/api/tests/test_gmail_tools.py`.
