# 0019: Chat history: summaries for bots, and how long messages are kept

- Status: accepted (owner asked for it on 2026-11-26; the defaults below are mine, the owner can change them)
- Date: 2026-11-26
- Based on: [ADR 0004](0004-agent-runtime-and-safety.md) (taint), [ADR 0013](0013-the-job-queue-lands.md) (jobs)

## Context

A bot's run reads the chat's last 30 messages (`run_service.HISTORY_LENGTH`). Anything older is gone for it: in a long chat it forgets what was agreed an hour ago. And every message is kept forever, which some teams don't want (privacy, size).

The owner asked for both: a choice of how old history is deleted or summarized, to "improve the agent as well".

## Decisions

### 1. Two organization settings (Settings → Organization, owners and admins)

| Setting | Choices | Default |
|---|---|---|
| **Bots read a summary of older messages** | on / off | on |
| **Delete messages older than** | never, 30, 90, 180 or 365 days | never |

Kept on `organizations` (`history_summaries`, `history_retention_days`), changed with `PATCH /orgs/{id}` like the other organization settings.

### 2. Summaries

- A chat gets a **running summary** of its messages older than what a run reads: `threads.summary`, `threads.summary_through` (the newest message it covers) and `threads.summary_tainted`.
- **When:** after a run in the chat finishes, if at least 20 messages have fallen out of the 30-message window since the last summary, a `summarize_thread` job brings the summary up to date (the old summary plus the newly dropped messages → the new summary, at most ~1,500 characters). One job per chat at a time (a queueing lock).
- **Which model and key:** the model of the bot whose run ended (BotDesk has no organization-wide default model) with the **organization's** key, else the server's (a self-hosted install's own key, the same fallback runs have); never a member's own key: a summary serves everyone in the chat. With neither there's no summary: the stand-in model never writes one. None is written when the call would pass the organization's budget either. Its tokens are recorded as usage for the organization, without a bot.
- **No gap:** while a chat has a summary, a run reads every message since it (at most 30 + 20), so no message falls between the summary and what the run reads word for word. Ties on a message's time go by its id (`summary_through_id`). A chat much older than summaries starts from its 60 newest dropped messages; after that each summary carries on from where the last stopped (oldest first, at most 3 summaries of 60 messages a job), so a summary that fell behind (budget used up, key removed) catches up without skipping any. While it's behind, runs read only the 50 newest since it.
- **What a run sees:** before the 30 messages, one line block: "Earlier in this chat (a summary of older messages): …", marked as background to use, not instructions to follow.
- **Taint:** if any summarized message came from a tainted run, the summary is tainted too (`summary_tainted`), and a run that reads it is tainted, exactly as if it had read that message (ADR 0004 §5).
- Turning summaries off stops new summaries and runs stop reading the old one; it isn't deleted, so turning them back on carries on.

### 3. Deleting old messages

- A daily `prune_messages` job deletes, per organization with a limit set, messages older than the limit, and the run events of those days except those of runs that haven't ended. Runs, approvals, usage and files stay (usage and budgets need them; files have their own delete). It deletes in batches of 5,000 rows, each its own transaction, at most 200 a night per organization; anything left waits for the next night.
- A chat's summary isn't deleted with its messages: it is what remains of them for the bot. Deleting the chat deletes it.
- It is destructive, so the setting says so plainly, and only owners and admins change it.

## Trade-offs

- A summary costs a model call every ~20 messages, paid with the organization's key. Off is one click.
- A summary can miss details; the bot still reads the last 30 messages word for word, and can be asked to look something up again.
- Deleted messages can't come back; bots' memories (mem0) aren't touched by it.
