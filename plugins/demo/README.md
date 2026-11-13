# botdesk-plugin-demo

Fake tools for trying BotDesk with no outside account. Plugin id: `demo`. Nothing here leaves your machine: "emails" are only recorded, and notes live in memory until the API restarts.

| Tool | Risk | Why it's here |
|---|---|---|
| `demo.current_time` | read | runs without asking |
| `demo.search_kb` | read | a fake knowledge-base search |
| `demo.create_note` | write-internal | changes something inside BotDesk, still no approval |
| `demo.draft_email` | write-external | a reversible change "in another app": asks unless Autonomous |
| `demo.send_email` | external-send | asks unless Autonomous; always asks in a tainted run |
| `demo.read_inbox` | read | returns outside text (with a prompt injection in it): taints the run |

It is also the reference plugin: it imports only [`botdesk_plugin_sdk`](../../packages/plugin-sdk/README.md), and the API finds it through its entry point in `pyproject.toml`:

```toml
[project.entry-points."botdesk.plugins"]
demo = "botdesk_demo:demo_plugin"
```

It loads when `demo` is in the API's `PLUGINS` setting (the default).

```bash
uv run --package botdesk-plugin-demo pytest plugins/demo   # from the repo root
```
