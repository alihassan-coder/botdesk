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
| **Chief** | The chief-of-staff bot. It splits work, hands the parts to specialist bots, and combines their results into one answer. It is an ordinary bot with the handoff tool and instructions to delegate, not a special type. |
| **Computer** | A bot's persistent cloud sandbox (desktop + browser). Default: one per bot. A member can watch it live or **take over**. |
| **Thread** | A conversation. `dm` = one member + one bot. `group` = several members and bots. |
| **Mention** | `@handle` inside a message. Mentioning a bot in the chat starts a run for it, whether a member or another bot wrote the message; mentioning a member notifies them. |
| **Lead** | The one bot in a group that answers a member's message that mentions no bot. Optional. |
| **Guest** | A bot that a member pulled into a DM with an @mention: it answers there once, and the DM stays with its own bot. |
| **Hop** | How far a run is from a person: a run started by a member's message is hop 0; one started by a bot's message or handoff is one more than that bot's run. Mentions and handoffs share one count, and chains stop at the hop limit. |
| **Handoff** | One bot deliberately giving a task to another bot of the organization, through a tool. Unlike a mention, it assigns the work, and the result comes back to the bot that handed it off ([ADR 0014](docs/adr/0014-handoffs-and-tasks.md)). |
| **Task** | The work one handoff assigns: who handed it off, the bot that owns it, what to do, its status (`queued`, `working`, `done`, `failed`, `cancelled`) and its result. Shown as a handoff card in the chat. _Avoid_: subtask, job, assignment. |
| **Run** | One piece of work by one bot, from a trigger to a final answer. It is a LangGraph graph and can pause: `waiting_approval` (a risky tool call waits for a person), `waiting_handoff` (it handed off tasks and continues once all of them have ended) or `needs_attention` (a tool may have half run; a person checks). A run started by a handoff is that task's **child run**; the run that handed off is its **parent**. A worker moves a run forward by taking **jobs** from the queue ([ADR 0013](docs/adr/0013-the-job-queue-lands.md)). |
| **Approval** | A run paused on a risky action. A member sees the exact action and approves, denies, or edits it. |
| **Approval status** | `pending`, then `approved`, `edited` (approved with changed arguments), `denied`, or `expired` (nobody answered in time, or the run was stopped). Expired counts as no. |
| **Tool call** | One use of a tool by a run, as the model asked for it. Recorded as a **tool execution** (`tool_executions`): `ready` / `waiting_approval` → `started` → `succeeded` / `failed`, or `denied`. Run + tool call id is its idempotency key, so it never runs twice. |
| **Policy** | Security level × risk class → `auto`, `ask` or `deny`, made stricter by taint. Every decision is saved with a **decision trace** saying why. |
| **Risk class** | How dangerous a tool action is: `read`, `write-internal`, `write-external` (a reversible change in another app: draft, label, calendar hold), `external-send`, `spend`, `destructive`, `credential` (changes who can reach what: forwarding, sharing, keys). |
| **Security level** | One of three: *Read only*, *Ask before acting* (default), *Autonomous within limits*. Maps each risk class to `auto` / `ask` / `deny` ([ADR 0004](docs/adr/0004-agent-runtime-and-safety.md)). The strictest of org, bot and routine wins. An org also has a **default security level**: the level a new bot starts at when whoever hires it doesn't pick one (a starting point, not a ceiling). |
| **Taint** | A mark on a run once it has read outside text (an email, a web page, an MCP result). After that, every action above `write-internal` asks for approval, even for Autonomous bots. |
| **Job** | A unit of background work in the queue (procrastinate): move a run forward, expire approvals, fire a routine. Deferred once, or periodic on a schedule. |
| **Run event** | One step of a run's progress (a token, a tool call, an approval card), saved in `run_events` and streamed to the chat. |
| **Routine** | A saved, repeatable task, either recorded by **follow along** (the bot watches a member do it) or created from chat, run on a schedule or trigger. |
| **Trigger** | What starts a run without a message: schedule, new email, webhook, follow-up timer, stalled thread. A plugin's trigger (Gmail's "React to new email") is switched on per bot; whoever switches it on is its **subscriber**: its events come to their DM with the bot, and they are its runs' requester. |
| **Plugin** | A self-contained source of tools described by a manifest: auth, tools (each with a risk class), triggers, settings. **Built in** plugins ship with the server (Gmail is the first); an **MCP server** is the other kind. A bot uses a plugin only through a binding. _Avoid_: integration, installation, app (except in UI copy "Connect apps"). |
| **Connector** | A plugin as listed on Connect apps (e.g. "Gmail"), whether or not anyone has connected it. |
| **Connection** | One authorised account on one connector (e.g. `ali@acme.dev` on Gmail), owned by a member, a bot (its own mailbox) or the org (shared). A member's own connection serves only runs whose requester is that member. _Avoid_: account, credential, integration. |
| **Binding** | A bot's permission to use one plugin: through which connection (if the plugin needs one), which of its tools, and with which settings. A bot's bindings are its **Tools**. |
| **Requester** | The member a run acts for: whoever wrote the message that started its chain, or who set up the trigger or routine that started it. |
| **MCP server** | A remote server speaking the Model Context Protocol that an org's admin added. One kind of plugin, private to that org; everything it says counts as outside text. |
| **Tool snapshot** | The exact tool list of an MCP server (names, descriptions, arguments) that an admin approved. A tool that no longer matches its snapshot is paused until approved again. |
| **Memory** | Facts a bot remembers about members and work (mem0). Visible and editable by members. |
| **Template** | A ready-made bot in the marketplace that an org can hire. Hiring one makes a bot with its instructions and plugins, at its security level or the org's default, whichever is stricter. One catalogue for every org (`apps/api/src/templates/catalogue.json`). |
| **Budget** | A monthly spending cap (calendar month, UTC) on a bot, and optionally on the whole organization. A bot that reaches either stops before its next model call and says so in the chat. 0 or empty = no limit. |
| **Model provider** | A service bots' models come from: Anthropic, OpenAI, Google Gemini, OpenRouter, Groq, or a **custom** OpenAI-compatible server (Ollama, LM Studio, vLLM). Its id is the kind (`groq`) or `custom-<id>`. |
| **Model id** | `provider:model`, e.g. `anthropic:claude-opus-5-5` or `custom-<id>:llama3.2:latest` (only the first colon splits). Empty = the instance's default model. |
| **Model key** | An organization's API key for a model provider (`provider_credentials`), added by owners and admins in Settings → Models & keys, checked live and encrypted at rest. People only ever see its last 4 characters. Key precedence for a run today: the org's key → the server's environment key → the stand-in model. Per-bot and per-member keys come later. |
