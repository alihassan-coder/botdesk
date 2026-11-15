# 0009: How bots work together in a chat

- Status: accepted
- Date: 2026-11-15
- Based on: the 2026-11-14 multi-bot test, [ADR 0004](0004-agent-runtime-and-safety.md) (runs, taint, concurrency), [GLOSSARY.md](../../GLOSSARY.md)

## Context

Until now only a person's message could start a run, and only for bots @mentioned in a group. Grok Bot's core idea is a team: bots pass work to each other and a chief of staff splits it up. Letting bots start each other's runs is easy; doing it without loops, runaway cost or taint laundering is the hard part. The API has no notion of a "Chief": it is an ordinary bot with that name.

## Decisions

1. **A bot's @mention starts a run, like a person's.** When a run's reply mentions another bot in the chat, that bot gets a run whose trigger is the reply. A bot never triggers itself.
2. **Hops.** Every run has a **hop** count: a person's message starts hop 0; a run started by a bot's message is one more than that message's run. The **hop limit is 3**. A mention that would go past it starts nothing, and the chat shows a short notice saying the chain stopped. A run also records the run that started it, so the chain can be traced.
3. **Pulling a bot into a DM.** In a DM, a member who @mentions another bot of the organization **pulls it in**: that bot replies once in the DM, as a guest. The DM stays a DM with its own bot. Only a member's mention pulls a bot in; bots can mention only bots already in the chat (or already pulled into it).
4. **Groups have a lead bot.** A group may have one **lead** bot, set when the group is created (the first bot picked, changeable later). A member's message in a group that mentions no bot goes to the lead. With no lead, nobody replies, as before.
5. **Taint travels with the chain.** A run started by a tainted run's reply starts tainted (this already follows from history-based taint, decided on 2026-11-14), so a chain can't launder outside instructions.
6. **Limits still hold.** One run at a time per chat, at most 2 running per bot, budgets and step limits apply to every run in a chain. A chain is a sequence of runs, never runs inside runs.
7. **Handoffs come next and build on this.** A handoff is a deliberate, recorded passing of a task (with a card in the chat and an owner), done through a tool. Mentions are conversation; handoffs are assignments.

## Trade-offs

- A hop limit of 3 can cut off a long but useful chain. It is a setting, and the notice tells people why it stopped.
- A guest reply in a DM means a DM can show messages from more than one bot. The chat list and the DM's title stay the DM's own bot.
- A lead bot is one more thing to set on a group, but it avoids special-casing a bot by its name.
