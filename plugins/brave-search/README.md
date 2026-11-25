# Brave Search plugin

Bots search the web with your organization's own [Brave Search API](https://brave.com/search/api/) key. Brave's free plan covers a few thousand searches a month; BotDesk adds nothing to the bill.

| Tool | Risk | What it does |
|---|---|---|
| `brave-search.search` | `read` | Searches the web and returns titles, addresses and short summaries (up to 10). Results are text from the web, so reading them taints the run: risky actions after it ask a person. |

To read a result, the bot opens it with the Browser plugin (`browser.open`).

## Turn it on

1. The server's operator adds `brave-search` to `PLUGINS` (for example `PLUGINS=demo,gmail,brave-search`) and restarts the API.
2. In **Connect apps**, connect **Brave Search** with your API key (from the Brave Search API dashboard). BotDesk keeps it encrypted and sends it only to `api.search.brave.com`, in the `X-Subscription-Token` header; the plugin never sees it.
3. Bots get the tool in their **Tools** tab, like any app without sign-in.

## Check it

```bash
uv run --package botdesk-plugin-brave-search pytest plugins/brave-search
uv run python -m botdesk_plugin_sdk manifest plugins/brave-search
uv run python -m botdesk_plugin_sdk check-imports plugins/brave-search
```
