# 0014: Handoffs and tasks

- Status: accepted (owner decisions 2026-11-16: report back, any bot in the organization, a card in the chat only)
- Date: 2026-11-16
- Based on: [ADR 0004](0004-agent-runtime-and-safety.md) (risk classes, taint, approvals), [ADR 0009](0009-bots-working-together.md) (hops, guests, "handoffs come next"), [ADR 0010](0010-connections-and-credentials.md) (requester, member connections), [ADR 0013](0013-the-job-queue-lands.md) (runs are jobs, one run at a time per chat), [agents-and-plugins.md §8](../architecture/agents-and-plugins.md#8-bots-working-together), the code as of 2026-11-16
- Contract for builders: [handoffs-contract.md](../architecture/handoffs-contract.md)

## Context

ADR 0009 let bots @mention each other. A mention is conversation: the mentioned bot answers in the chat, and nobody is waiting for that answer. Grok Bot's Chief works differently: it splits a request, gives each part to a specialist, waits, and then combines their results into one answer. That needs three things mentions don't have: an explicit assignment with an owner, a way for the bot that assigned the work to **get the results back**, and a way to wait for them that doesn't block the chat.

Waiting is the hard part. Every run in a chat shares the job lock `chat:{thread_id}`, and only one run per chat may be `running` (ADR 0013 §2). The specialists work in the same chat, so a Chief that waited while still holding its turn would wait forever.

## Decisions

1. **A handoff is a tool call, `team.handoff`.** Its arguments are the teammate's `@handle`, the task, and optional context. It belongs to a core plugin, **Team** (id `team`), which the server always loads (it isn't in `PLUGINS`) and which a bot gets through a binding like any other plugin. Every bot has the binding switched on by default (new bots and a backfill), and members can switch it off on the bot's Tools tab. **The Chief is an ordinary bot** with this tool and instructions that tell it to delegate. There is no "Chief" type in the API.
2. **Each handoff creates a task.** A task records who handed off (the parent run and its bot), who owns the work (the target bot), what to do, its status (`queued` → `working` → `done` / `failed` / `cancelled`), and its result. The target does the task in a **child run** in the same chat, whose parent is the run that handed off.
3. **Results come back to the parent run.** After the model's step that handed off (one or more `team.handoff` calls in one answer), the parent run **pauses** in a new status, **`waiting_handoff`**. It is a LangGraph `interrupt`, like an approval: the run's job ends and it releases the chat's lock, so the children can run. When the last of its open tasks ends, the parent is **resumed once**: a `run_bot` job is deferred in the same transaction that ended that task, with the parent's row locked so two tasks ending at the same moment can't both miss (or both trigger) the resume. The parent's model then reads every child's final reply and status, and carries on.
4. **The tool always runs at once.** `team.handoff` is `write-internal`, so the policy says `auto` at every security level, tainted or not. Creating the task, the child run and its job, and recording the tool call as `succeeded` happen in **one transaction**, so a handoff can never be half done and never needs `needs_attention`.
5. **Targets:** any bot in the organization except the bot itself and any bot already in the chain above it (no cycles). In a DM, a target that isn't the DM's own bot answers as a **guest** (ADR 0009 §3); in a group, a target that isn't in the group answers there for that task without joining the group.
6. **Limits:**
   - **Hops:** a child run is one hop further than its parent. Handoffs and mentions share one count and one limit (`BOT_HOP_LIMIT`, 3). A handoff past it is refused, and the model is told why.
   - At most **5 tasks per run** over its whole life, and at most **20 open tasks per organization**.
   - A task that isn't finished **60 minutes** after it was created fails as timed out. Its child run is stopped, and the parent carries on. Waiting for an approval counts towards those minutes.
   - The child is held to its own budget, step and time limits.
7. **Children run one at a time.** They work in the parent's chat, so "one run at a time per chat" applies: three handoffs in one step run one after another. Waiting for all of them is the same as waiting for the last one.
8. **Safety travels down the chain, never up a level:**
   - **Taint:** a child starts tainted if its parent is tainted. A parent becomes tainted when a tainted child's result comes back. Handing off can't wash outside text clean in either direction.
   - **Security level:** the child's effective level is the strictest of its own level and its parent's effective level, the same way a routine can only make a bot stricter. A *Read only* Chief can't get an *Autonomous* bot to act for it. The child's approvals are its own and show in the chat as usual.
   - **Requester:** the child inherits its parent's requester. The connections rule of ADR 0010 is unchanged: a member's own connection serves only that member's runs in their own DM with that same bot. So a child only uses a member's connection when the chat is that member's DM with the child's own bot, and never in a group.
   - **Memory:** child runs are started by a bot (hop > 0), so they save no memories (ADR 0009).
   - The child reads the task as its request, not as untrusted bot output: a handoff is an assignment. Taint and the level cap above are what make that safe.
9. **Stop:**
   - Stop on a parent cancels all of its open tasks and stops their child runs, all the way down the chain.
   - Stop on a child **fails only that task** ("Stopped"), and the parent resumes with that result.
   - A child that runs out of budget fails its task with the budget message.
   - A run that ends in any way while it still has open tasks cancels them.
10. **In the chat:** when a run pauses for tasks, the words it has written so far are saved as a message, with one **handoff card** per task. That message is also the children's trigger. Each card shows who handed what to whom, its status and a preview of the result. It is rewritten in place whenever its task changes, and a `task_updated` event updates it live. Each child's reply is an ordinary message from that bot. After the results come back, the parent writes a **new** message, its final answer. **No Tasks page and no task list in the bot pane for now.**
11. **No new routes.** The web reads tasks through the handoff cards in messages and through run events. The active-runs list already includes paused runs, and `waiting_handoff` is one of them.

## Considered options

- **Wait inside the parent's job** (poll, or `await` the children). Rejected: it holds the chat's lock that the children need, so it deadlocks, and a waiting run would hold a worker slot.
- **Children as a new message the parent "mentions"** (reuse ADR 0009 routing). Rejected: mentions don't report back, and a mention can't fail, time out or be owned.
- **The handoff's tool result *is* the child's result**, holding each tool result back until the child finishes. Rejected: when one model step makes several calls, their results would arrive out of order and long after the call. Instead, the tool answers at once ("handed off"), and all results arrive together as one message when the parent resumes.
- **Children with their own level, unchanged** (the first reading of agents-and-plugins §8). Rejected because it lets a strict bot reach a looser one's powers. The child still uses its own level when that one is stricter.
- **Run children side by side in separate chats.** Rejected for v1: the owner wants the work visible in the same chat. It's slower (one at a time), but people can follow it.

## Consequences

- New table `tasks`, a new run status `waiting_handoff` (a paused status, so Stop works on it), and a new column `runs.level_cap`. Three graph nodes are added (`hand_off`, `save_progress`, `wait_for_tasks`); none is renamed, so paused checkpoints still load (ADR 0004 §8).
- A run can now write more than one message: one per pause for tasks, then its reply. `runs.reply_message_id` stays the final reply.
- New jobs: `expire_tasks` (every minute). `recover_runs` also closes tasks whose child already ended and resumes parents that should be moving.
- The handoff tool doesn't show a "Used …" tool line. Its card is the record people see.
- A Chief's turn is slower than a single bot's: each child is a full run, one after another. The hop limit and the per-run cap bound the cost. Budgets still apply to every run.
