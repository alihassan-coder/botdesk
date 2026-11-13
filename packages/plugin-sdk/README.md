# botdesk-plugin-sdk

The contract between [BotDesk](https://github.com/alihassan-coder/botdesk) and its plugins. A plugin adds **tools** that bots can use: look something up, draft an email, create a ticket. You write the tools; BotDesk decides when a person has to approve a call.

The SDK is small on purpose. It depends only on Pydantic. It has no database, no web framework and no LLM library, and a plugin never imports the BotDesk app.

| What | Where |
|---|---|
| `PluginManifest` | who the plugin is and which tools it adds |
| `ToolSpec` | one tool: name, title, description, args model, risk class, handler, flags |
| `RiskClass` / `RISK_CLASSES` | the 7 risk classes, least to most dangerous |
| `Egress` | `fixed` (always the same service) or `open` (any address) |
| `ToolContext` | what a handler gets besides its arguments |
| `ToolResult` | what a handler returns: a JSON-friendly dict |
| `NoArgs` | the args model for a tool without arguments |
| `validate_manifest`, `PluginError` | the checks BotDesk runs before loading a plugin |
| `botdesk_plugin_sdk.testing` | `call_tool` and `make_context`, to test tools without the app |
| `ENTRY_POINT_GROUP` | `"botdesk.plugins"`, where BotDesk looks for plugins |

## Write your first plugin in 5 minutes

We'll build `weather`, a plugin with one tool. Inside the BotDesk repo, plugins live in `plugins/<name>/`; copying [`plugins/demo`](../../plugins/demo) is the quickest start. In your own repo the layout is the same.

**1. The package.** `plugins/weather/pyproject.toml`:

```toml
[project]
name = "botdesk-plugin-weather"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["botdesk-plugin-sdk", "httpx"]

# BotDesk finds plugins here. The name is the plugin id; the value returns the manifest.
[project.entry-points."botdesk.plugins"]
weather = "botdesk_weather:weather_plugin"

[tool.uv.sources]
botdesk-plugin-sdk = { workspace = true }   # only inside the BotDesk repo

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/botdesk_weather"]
```

**2. The tool.** `plugins/weather/src/botdesk_weather/__init__.py`:

```python
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from botdesk_plugin_sdk import PluginManifest, ToolContext, ToolResult, ToolSpec


class ForecastArgs(BaseModel):
    """The arguments. The model sees this JSON schema, so describe every field."""

    city: str = Field(min_length=1, max_length=80, description="City name, e.g. 'Lahore'")


async def forecast(args: ForecastArgs, ctx: ToolContext) -> ToolResult:
    ctx.logger.info("forecast for %s", args.city)
    async with httpx.AsyncClient(timeout=10) as client:
        reply = await client.get(f"https://wttr.in/{quote(args.city)}", params={"format": "j1"})
        reply.raise_for_status()
    today = reply.json()["weather"][0]
    return {"city": args.city, "maxC": today["maxtempC"], "minC": today["mintempC"]}


def weather_plugin() -> PluginManifest:
    return PluginManifest(
        id="weather",
        name="Weather",
        version="0.1.0",
        description="Today's forecast for a city.",
        tools=(
            ToolSpec(
                name="forecast",
                title="Check the weather",
                description="Get today's highest and lowest temperature for a city.",
                args_model=ForecastArgs,
                risk="read",
                handler=forecast,
                idempotent=True,  # safe to run again after a crash
                untrusted_output=False,  # True if it returns outside text (emails, web pages)
            ),
        ),
    )
```

**3. A test.** `plugins/weather/tests/test_weather.py`:

```python
from botdesk_plugin_sdk import validate_manifest
from botdesk_weather import weather_plugin


def test_the_manifest_is_valid() -> None:
    validate_manifest(weather_plugin())
```

`botdesk_plugin_sdk.testing.call_tool(weather_plugin(), "forecast", {"city": "Lahore"})` runs a tool the way BotDesk would (validates the arguments, then calls the handler with a test context). Use it with a fake HTTP client for real tests.

**4. Run it.** From the repo root: `uv sync --all-packages`, then `uv run --package botdesk-plugin-weather pytest plugins/weather`.

**5. Turn it on.** Add the plugin to the API's dependencies (`apps/api/pyproject.toml`, plus a `[tool.uv.sources]` line), add its id to the `PLUGINS` setting (`PLUGINS=demo,weather` in `apps/api/.env`) and start the API. Being installed is not enough: only plugins named in `PLUGINS` load. Ask a bot "what's the weather in Lahore?".

## Choosing a risk class

Pick what the tool *does*, not how likely it is to go wrong. BotDesk's policy table decides when to ask.

| Risk class | Use it for |
|---|---|
| `read` | looking something up, changing nothing |
| `write-internal` | changing something inside BotDesk (a note, a task) |
| `write-external` | a reversible change in another app (a draft, a label) |
| `external-send` | anything that leaves: an email, a message, a post |
| `spend` | anything that costs money |
| `destructive` | deleting or overwriting, can't be undone |
| `credential` | passwords, tokens or keys |

Also set:

- `egress="open"` when the tool can reach any address (a "fetch this URL" tool). In a run that has read outside text it then counts as `external-send`.
- `untrusted_output=True` when it returns text written by someone outside (an email body, a web page). Reading it "taints" the run, and risky tools ask from then on.
- `idempotent=True` only when running it twice does no harm. Other tools stop and ask a person after a crash instead of running again. For services that accept an idempotency key, pass on `ctx.idempotency_key`; it stays the same across retries of one call.
- `summarize=lambda args: f"Send an email to {args.to}"` for a clearer approval card.

## The rules BotDesk checks at load time

A plugin that breaks one is skipped with a log line saying why; it never stops the API.

- The plugin id is lowercase letters, digits and dashes, starting with a letter, and matches the entry-point name.
- Tool names are lowercase letters, digits and underscores, unique in the plugin.
- Every tool has a title, a description, a known risk class and egress.
- `args_model` is a Pydantic `BaseModel` class.
- The handler is an `async def`. A blocking handler would stall every other bot on the server.

Run the same checks in your tests with `validate_manifest(your_plugin())`.

## What a handler may and may not do

`ToolContext` carries the organization, bot and run ids, the tool call id, the idempotency key and a logger. It has no database session and no settings: a plugin gets only what BotDesk hands it. Return a small JSON-friendly dict, never secrets. Raise an exception when something fails; BotDesk records the error and the bot sees a short message.

## Versions and releases

The SDK follows semantic versioning on its own clock (`sdk-v0.1.0`), separate from the BotDesk app ([ADR 0006](../../docs/adr/0006-repo-structure-plugins-and-project.md)). `PluginManifest.to_json()` carries a `manifestVersion`, so the app can tell which manifest shape it is reading.

Releasing (maintainers; not automated yet):

1. Bump `version` in `pyproject.toml` and `__version__` in `src/botdesk_plugin_sdk/__init__.py`, commit as `chore(sdk): release 0.x.y`, and tag `sdk-v0.x.y`.
2. `uv build --package botdesk-plugin-sdk` from the repo root (writes `dist/`).
3. `uv publish dist/botdesk_plugin_sdk-*`, signed in to PyPI with Trusted Publishing from a GitHub Actions job (no stored password).

release-please (manifest mode) will take over steps 1 and 3 with the first app release (build step 4).

## Licence

MIT.
