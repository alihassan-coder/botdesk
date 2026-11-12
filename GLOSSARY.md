# Glossary

The words BotDesk uses for its domain. Use these exact terms in code, UI copy, docs and prompts.

| Term | Meaning |
|---|---|
| **Org** | A tenant: a company or team. Every piece of user content belongs to exactly one org. |
| **Organization** | The full word for **Org**, used in UI copy ("Manage organization"). Same thing. |
| **Member** | A human in an org, with a role (`owner`, `admin`, `member`). |
| **Invitation** | An offer for someone to join an org as a member with a given role. |
| **Session** | A signed-in member on one device. Signing out ends it. |
| **Bot** | An AI teammate: a name, `@handle`, role, instructions, model, tools, memory, security level, budget, and usually its own computer. |
| **Chief** | The chief-of-staff bot. It splits work and hands it to specialist bots. It is an ordinary bot with delegation tools, not a special type. |
| **Computer** | A bot's persistent cloud sandbox (desktop + browser). Default: one per bot. A member can watch it live or **take over**. |
| **Thread** | A conversation. `dm` = one member + one bot. `group` = several members and bots. |
| **Mention** | `@handle` inside a message. Mentioning a bot starts a run for it; mentioning a member notifies them. |
| **Handoff** | One bot passing a task to another bot, visible in the thread. |
| **Run** | One piece of work by one bot, from a trigger to a final answer. It is a LangGraph graph, survives restarts and can pause for an approval. A worker moves it forward by taking **jobs** from the queue. |
| **Approval** | A run paused on a risky action. A member sees the exact action and approves, denies, or edits it. |
| **Risk class** | How dangerous a tool action is: `read`, `write-internal`, `write-external` (a reversible change in another app: draft, label, calendar hold), `external-send`, `spend`, `destructive`, `credential`. |
| **Security level** | One of three: *Read only*, *Ask before acting* (default), *Autonomous within limits*. Maps each risk class to `auto` / `ask` / `deny` ([ADR 0004](docs/adr/0004-agent-runtime-and-safety.md)). The strictest of org, bot and routine wins. |
| **Taint** | A mark on a run once it has read outside text (an email, a web page, an MCP result). After that, every action above `write-internal` asks for approval, even for Autonomous bots. |
| **Job** | A unit of background work in the queue (procrastinate): run a bot, expire an approval, fire a routine. |
| **Run event** | One step of a run's progress (a token, a tool call, an approval card), saved in `run_events` and streamed to the chat. |
| **Routine** | A saved, repeatable task, either recorded by **follow along** (the bot watches a member do it) or created from chat, run on a schedule or trigger. |
| **Trigger** | What starts a run without a message: schedule, new email, webhook, follow-up timer, stalled thread. |
| **Plugin** | A self-contained integration described by a manifest: auth, tools (each with a risk class), triggers, settings. Gmail is the first. A remote MCP server is one kind of plugin. |
| **Connector** | A plugin as listed in the catalog (e.g. "Gmail"). |
| **Connection** | A connector authorised for a member, bot or org (e.g. `ali@acme.dev` on Gmail). |
| **Memory** | Facts a bot remembers about members and work (mem0). Visible and editable by members. |
| **Template** | A ready-made bot in the marketplace that an org can hire. |
| **Budget** | A spending cap on a bot. A bot that reaches it is paused. |
| **Model key** | An API key for a model provider. Key precedence for a run: bot override → org-enforced → member's own → org default. |
