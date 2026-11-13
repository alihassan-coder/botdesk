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
| **Run** | One piece of work by one bot, from a trigger to a final answer. It is a LangGraph graph and can pause: `waiting_approval` (a risky tool call waits for a person) or `needs_attention` (a tool may have half run; a person checks). For now the API process runs it ([ADR 0007](docs/adr/0007-runs-in-the-api-process-for-now.md)); later a worker moves it forward by taking **jobs** from the queue. |
| **Approval** | A run paused on a risky action. A member sees the exact action and approves, denies, or edits it. |
| **Approval status** | `pending`, then `approved`, `edited` (approved with changed arguments), `denied`, or `expired` (nobody answered in time, or the run was stopped). Expired counts as no. |
| **Tool call** | One use of a tool by a run, as the model asked for it. Recorded as a **tool execution** (`tool_executions`): `ready` / `waiting_approval` → `started` → `succeeded` / `failed`, or `denied`. Run + tool call id is its idempotency key, so it never runs twice. |
| **Policy** | Security level × risk class → `auto`, `ask` or `deny`, made stricter by taint. Every decision is saved with a **decision trace** saying why. |
| **Risk class** | How dangerous a tool action is: `read`, `write-internal`, `write-external` (a reversible change in another app: draft, label, calendar hold), `external-send`, `spend`, `destructive`, `credential`. |
| **Security level** | One of three: *Read only*, *Ask before acting* (default), *Autonomous within limits*. Maps each risk class to `auto` / `ask` / `deny` ([ADR 0004](docs/adr/0004-agent-runtime-and-safety.md)). The strictest of org, bot and routine wins. |
| **Taint** | A mark on a run once it has read outside text (an email, a web page, an MCP result). After that, every action above `write-internal` asks for approval, even for Autonomous bots. |
| **Job** | A unit of background work in the queue (procrastinate, planned): run a bot, expire an approval, fire a routine. |
| **Run event** | One step of a run's progress (a token, a tool call, an approval card), saved in `run_events` and streamed to the chat. |
| **Routine** | A saved, repeatable task, either recorded by **follow along** (the bot watches a member do it) or created from chat, run on a schedule or trigger. |
| **Trigger** | What starts a run without a message: schedule, new email, webhook, follow-up timer, stalled thread. |
| **Plugin** | A self-contained integration described by a manifest: auth, tools (each with a risk class), triggers, settings. Gmail is the first. A remote MCP server is one kind of plugin. |
| **Connector** | A plugin as listed in the catalog (e.g. "Gmail"). |
| **Connection** | A connector authorised for a member, bot or org (e.g. `ali@acme.dev` on Gmail). |
| **Memory** | Facts a bot remembers about members and work (mem0). Visible and editable by members. |
| **Template** | A ready-made bot in the marketplace that an org can hire. |
| **Budget** | A monthly spending cap (calendar month, UTC) on a bot, and optionally on the whole organization. A bot that reaches either stops before its next model call and says so in the chat. 0 or empty = no limit. |
| **Model provider** | A service bots' models come from: Anthropic, OpenAI, Google Gemini, OpenRouter, Groq, or a **custom** OpenAI-compatible server (Ollama, LM Studio, vLLM). Its id is the kind (`groq`) or `custom-<id>`. |
| **Model id** | `provider:model`, e.g. `anthropic:claude-opus-5-5` or `custom-<id>:llama3.2:latest` (only the first colon splits). Empty = the instance's default model. |
| **Model key** | An organization's API key for a model provider (`provider_credentials`), added by owners and admins in Settings → Models & keys, checked live and encrypted at rest. People only ever see its last 4 characters. Key precedence for a run today: the org's key → the server's environment key → the stand-in model. Per-bot and per-member keys come later. |
