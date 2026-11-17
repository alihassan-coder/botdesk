# 0015: Gmail reads attachments, sends formatted mail and sends saved drafts

- Status: accepted (owner approved the Gmail extras on 2026-11-17)
- Date: 2026-11-17
- Changes: [ADR 0011](0011-gmail-plugin.md) §3, which listed attachments and HTML compose as "not in v1" and said send cards show the full body

## Context

The owner asked for the Gmail extras: read attachments, send formatted mail, and send a draft that's already in the mailbox. Each one widens what a bot can read or send, so each needs a rule that keeps the approval card honest and keeps outside text untrusted.

## Decisions

1. **Attachments are read as text only.** `gmail.read_attachment` returns text-like types (text, HTML converted to text, JSON, CSV, XML), capped and inside an `<email>` block. It is `read` risk with untrusted output, so it taints the run. PDFs, images and Office files are refused with a reason, not downloaded. An attachment is named by its MIME part, because Gmail's attachment ids change between reads.
2. **Formatted mail comes from Markdown we convert, never from HTML the model writes.** `gmail.send` and `gmail.create_draft` take `format: "markdown"` and send `multipart/alternative`: the text as written, plus HTML that BotDesk generates. The model's own HTML is escaped, only `http(s)` and `mailto` links become links, and `format: "html"` is refused. Plain text stays the default.
3. **Sending a saved draft is checked at send time.** An approval card can only show a call's arguments, so `gmail.send_draft` carries the draft's recipients and subject, and the card shows them. Right before sending, the tool fetches the draft and sends it **only if To, Cc, Bcc and Subject still match exactly**. If they don't, nothing is sent. The card doesn't show the draft's body; the person can open the draft in Gmail.
4. **Listing drafts taints the run**, because reply drafts quote outside mail.

## Trade-offs

- The `send_draft` card is less complete than the `send` card (no body). The exact-match check keeps a draft edited after approval from going out.
- Reading an attachment costs one extra request to find its current id.
- Outgoing attachments and reading PDF text are still not supported.
