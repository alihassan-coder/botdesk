# 0022: Messages while a bot is working: send now, or queue

- Status: accepted (owner asked for it on 2026-11-27; the design below is mine)
- Date: 2026-11-27
- Based on: [ADR 0004](0004-agent-runtime-and-safety.md) (runs), [ADR 0013](0013-the-job-queue-lands.md) (one run at a time per chat)

## Context

A chat runs one run at a time. A message sent while a bot works gets a queued run that starts after the current one. The bot doing the work never sees the message: if you notice it going the wrong way ("use the GitHub tools instead", "you'll need to install Node 22"), you can only stop it and start over, or wait for it to finish the wrong thing.

The owner asked for a choice when sending while a bot works: **send now**, or **after the bot finishes**.

## Decisions

### 1. Two ways to send while a bot is working

- **Send now** (Enter, the default while a bot works): the bot reads your message **at its next step**, between two tool calls, and carries on with it in mind. Nothing it did is lost.
- **Queue** (the send menu, or Alt+Enter): the message waits and the bot answers it **after it finishes** the current work. This is today's behaviour.
- **Stop** stays as it was: it ends the current work.

### 2. How "send now" works

- The message is saved as usual, with a queued run as usual, so it is **always answered**: if the working run ends before its next step, that queued run answers it next, as today.
- The queued run is marked `runs.deliver_now`. Before each model call, a working run **takes** the queued `deliver_now` runs of **its own bot in its own chat whose message is from its own requester** (oldest first):
  - Their runs are cancelled with the note "Read by the run that was working".
  - Their messages join the run's conversation as "<name> sent a new message while you were working: …". The model call that follows sees them.
  - The cancel is an atomic `UPDATE … WHERE status = 'queued' RETURNING`, so a message is either taken or answered by its own run, never both and never neither.
- **Only the run's requester can steer it.** In a group, another member's message never changes a run acting for someone else: it waits for its own run, as before.
- A run **waiting for your approval** isn't working, and it doesn't hold up the chat: a message sent then is answered right away by its own run, as today. Only a run that is running (or queued ahead of it) can take a message.
- Files sent with a "send now" message go in as a line naming them; the bot reads them with its tools, as it does with any message's files.

### 3. What you see

- While a bot works, the send button offers **Send now** and **Queue**, and the hint under the box says which one Enter does.
- A message the working run took shows "Read while working" under it while the chat is open (a `message_read` event). Its cancelled run disappears from the chat's working runs at once (`run_finished`).

## Trade-offs

- A message can wait a while if the bot is in a long tool call (up to the tool's timeout). It's read at the next step, never mid-call.
- One more column (`runs.deliver_now`). The rest reuses queued runs, so a crash or restart loses nothing: an untaken message is answered by its own run.
