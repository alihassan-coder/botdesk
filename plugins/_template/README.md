# Plugin template

Copy this folder to start a BotDesk plugin. It has two fake tools (no network), one of each kind you'll usually write:

| Tool | Risk | Shows |
|---|---|---|
| `template.look_up_order` | `read` | an args model with described fields; runs without asking |
| `template.send_message` | `external-send` | something leaving: asks a person first; uses `ctx.idempotency_key` and an approval-card summary |

The full guide is [docs/plugins/README.md](../../docs/plugins/README.md). The SDK reference is [packages/plugin-sdk](../../packages/plugin-sdk/README.md).

## Copy and rename

From the repo root, for a plugin called `calendar`:

```bash
cp -r plugins/_template plugins/calendar
mv plugins/calendar/src/botdesk_template plugins/calendar/src/botdesk_calendar
rm plugins/calendar/manifest.json
```

Then replace `template` everywhere in the copy:

| File | Change |
|---|---|
| `pyproject.toml` | `name = "botdesk-plugin-calendar"`, a real `description`; entry point `calendar = "botdesk_calendar:calendar_plugin"`; `packages = ["src/botdesk_calendar"]` |
| `package.json` | `"name": "@botdesk/plugin-calendar"` |
| `src/botdesk_calendar/__init__.py` | `template_plugin` → `calendar_plugin`, `id="calendar"`, `name`, `description`, the tools |
| `tests/test_template_plugin.py` | rename to `test_calendar_plugin.py`, import from `botdesk_calendar` |
| `README.md` | this file: say what the plugin reads, what it can change and which scopes it asks for |

The entry-point name (`calendar`) must equal the manifest's `id`. `grep -rn template plugins/calendar` should find nothing when you're done.

## Calling a service on someone's account

The template's tools are fake. A real plugin that calls another app's API on someone's account adds two fields to its manifest (version 2), then calls the API through `ctx.http`:

```python
PluginManifest(
    ...,
    auth=ApiKeyAuth(header="X-Api-Key"),  # people paste a key in Connect apps; or OAuth2Auth(...)
    egress=("api.example.com",),  # the only hosts ctx.http may call
)


async def look_up_order(args: LookUpOrderArgs, ctx: ToolContext) -> ToolResult:
    response = await ctx.http.request("GET", f"https://api.example.com/orders/{args.order_id}")
    return {"found": response.ok, "order": response.json() if response.ok else None}
```

BotDesk adds the connection's credential to each request, refuses other hosts, plain `http`, redirects and private addresses, and caps size and time. The plugin never sees a token. Test it with `FakeHttp` (see the SDK README). `plugins/demo`'s `call_api` is a working example.

## Check it

```bash
uv sync --all-packages                                            # the copy joins the uv workspace
uv run --package botdesk-plugin-calendar pytest plugins/calendar
uv run python -m botdesk_plugin_sdk manifest plugins/calendar     # writes manifest.json; commit it
uv run python -m botdesk_plugin_sdk check-imports plugins/calendar
```

`pnpm check` also runs ruff, mypy and pytest for it, and CI fails if `manifest.json` is out of date or the plugin imports something it doesn't declare.

## Why this folder isn't installed

`plugins/_template` is excluded from the uv workspace and the pnpm workspace, so BotDesk never loads a plugin called `template`. Its `pyproject.toml` sets `pythonpath` (pytest) and `mypy_path` to `src`, so its own checks run without installing it. CI checks it in the "Check the plugin template" step.
