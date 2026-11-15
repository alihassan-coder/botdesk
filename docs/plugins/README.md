# Writing a plugin

A **plugin** adds tools that bots can use: look something up, draft an email, create a ticket ([GLOSSARY](../../GLOSSARY.md)). You write the tools and say how risky each one is; BotDesk decides when a person has to approve a call. A plugin is a small Python package that depends only on [`botdesk-plugin-sdk`](../../packages/plugin-sdk/README.md), never on the BotDesk app.

This guide is for **built-in plugins**, the ones in this repo's `plugins/` folder. Plugins from other people are MCP servers in v1 (see [the last section](#third-party-plugins-are-mcp-servers-in-v1)).

## 1. Copy the template

```bash
cp -r plugins/_template plugins/calendar
```

[`plugins/_template/README.md`](../../plugins/_template/README.md) lists every name to change (package, import name, entry point, plugin id, `package.json`). The plugin id is lowercase letters, digits and dashes, and the entry-point name in `pyproject.toml` must be the same id. [`plugins/demo`](../../plugins/demo) is a bigger example with seven tools; its `call_api` calls a web service with a connected API key.

## 2. Write the tools

Each tool is a `ToolSpec` in the list your entry-point function returns:

- **Arguments** are a Pydantic model (`args_model`). The model is shown its JSON schema and BotDesk validates every call against it, so the handler only sees clean input. Describe each field with `Field(description=...)`.
- **The handler** is an `async def handler(args, ctx) -> dict`. `ctx` is a `ToolContext`: org, bot and run ids, the tool call id, `idempotency_key`, a `logger`, and `http` / `connection` / `settings`. It has no database and no token: a plugin gets only what BotDesk hands it.
- **Calling another app** (manifest version 2): declare `auth=ApiKeyAuth(...)` or `OAuth2Auth(...)` and `egress=("api.example.com",)` on the manifest, then call `await ctx.http.request("GET", "https://api.example.com/...")`. BotDesk adds the connected account's credential, allows only those hosts over https, and refuses redirects and private addresses. Test with `FakeHttp`. Details: [SDK README](../../packages/plugin-sdk/README.md#calling-another-app-auth-egress-and-ctxhttp-manifest-version-2).
- **Return** a small JSON-friendly dict, never secrets. **Raise** when something fails; the bot sees a short message.
- **Imports:** the standard library, your own package, the SDK and the libraries listed under `[project] dependencies`. CI checks this (step 5).

## 3. Pick a risk class

Pick what the tool *does*, not how likely it is to go wrong. The [security level](../../GLOSSARY.md) of the bot turns the risk class into run, ask or refuse ([ADR 0004 §4](../adr/0004-agent-runtime-and-safety.md#decisions) has the table):

| Risk class | Use it for | Read only | Ask before acting | Autonomous |
|---|---|---|---|---|
| `read` | looking something up, changing nothing | auto | auto | auto |
| `write-internal` | changing something inside BotDesk (a note, a task) | auto | auto | auto |
| `write-external` | a reversible change in another app (a draft, a label) | deny | ask | auto |
| `external-send` | anything that leaves: an email, a message, a post | deny | ask | auto |
| `spend` | anything that costs money | deny | ask | ask |
| `destructive` | deleting or overwriting, can't be undone | deny | ask | ask |
| `credential` | passwords, tokens or keys | deny | ask | ask |

When in doubt, pick the riskier class. Also set:

- `untrusted_output=True` when the tool returns text written by someone outside (an email body, a web page). It taints the run: every later call above `write-internal` asks a person, even for Autonomous bots.
- `egress="open"` when the tool can reach any address (a "fetch this URL" tool).
- `idempotent=True` only when running it twice does no harm. Other tools stop and ask after a crash instead of running again. Pass `ctx.idempotency_key` to services that accept one.
- `summarize=` a function that returns the line on the approval card ("Send a message to #launch").

## 4. Test it

No app, no database, no network:

```python
from botdesk_plugin_sdk import validate_manifest
from botdesk_plugin_sdk.testing import call_tool, make_context

def test_the_manifest_is_valid() -> None:
    validate_manifest(calendar_plugin())          # the same checks BotDesk runs at load

async def test_create_event() -> None:
    result = await call_tool(calendar_plugin(), "create_event", {"title": "Launch"}, make_context())
```

`call_tool` validates the arguments and runs the handler the way BotDesk would; it does not apply the approval policy (that's the app's job). Run the tests with `uv sync --all-packages`, then `uv run --package botdesk-plugin-calendar pytest plugins/calendar`. `pnpm check` runs ruff, mypy (strict) and pytest for every plugin.

## 5. Regenerate the manifest

Every plugin checks in a `manifest.json` generated from its code: id, version, every tool with its risk class, flags and argument schema. Reviewers see a risk or argument change as a diff, and CI fails if the file is stale.

```bash
uv run python -m botdesk_plugin_sdk manifest plugins/calendar       # write it; commit the result
uv run python -m botdesk_plugin_sdk manifest --check plugins/*/     # what CI runs
uv run python -m botdesk_plugin_sdk check-imports plugins/calendar  # the import rule, also in CI
```

The file is stable: keys and tools are sorted, so reordering code doesn't change it.

## 6. Turn it on

1. Add the plugin to the API: a dependency in `apps/api/pyproject.toml` plus a `[tool.uv.sources]` line (`botdesk-plugin-calendar = { workspace = true }`), then `uv lock`.
2. Add its id to the **`PLUGINS`** allowlist: `PLUGINS=demo,calendar` in `apps/api/.env`. Installed is not enough: only ids in `PLUGINS` load.
3. Start the API. `GET /api/v1/orgs/{id}/plugins` (the Connect apps page) lists it. A plugin that fails the load checks is skipped with one log line saying why; the API still starts.

A plugin that talks to an outside service needs a README saying what it reads, what it can change and which scopes it asks for.

## Third-party plugins are MCP servers in v1

Python plugins run inside the BotDesk server with its permissions, so only plugins in this repo (reviewed like any other code) are Python plugins. Everyone else connects an **MCP server** ([ADR 0006 §4](../adr/0006-repo-structure-plugins-and-project.md#decisions)):

- BotDesk sets each MCP tool's risk class; the server's own hints are ignored.
- Every MCP tool starts as `external-send`, so it asks.
- Tool lists are hash-pinned: a changed tool needs approval again.

No-code HTTP plugins come after MCP; sandboxed third-party Python only if someone needs it. If you want a tool for an app BotDesk doesn't cover, write an MCP server, or send a built-in plugin here as a pull request.
