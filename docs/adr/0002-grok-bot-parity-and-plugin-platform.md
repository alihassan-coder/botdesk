# 0002 — Grok Bot parity, plugin-based integrations, security levels, approvals

- Status: accepted
- Date: 2026-11-11

## Decisions

1. **Full Grok Bot parity.** BotDesk matches all of Grok Bot's features, and its UI follows Grok Bot's layout and flows closely (with our own brand: see [0001](0001-product-scope-and-deployment.md)). The teardown in `docs/research/grok-bot-teardown.md` is the reference.
2. **First integration: Gmail only.** We ship one integration and do it well.
3. **Integrations are plugins, built to scale to hundreds.** Every integration (Gmail first, then Calendar, Slack, GitHub…) is a self-contained plugin with a manifest: its auth method, the tools it offers, the risk level of each tool, triggers and settings. Adding integration #2 or #200 needs no change to the core. Remote MCP servers fit in as one more kind of plugin.
4. **Learn from DeepSeek Harness.** [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (MIT, Aug 2026) makes everything a plugin on the Cordis kernel: model adapters, tools, session log and agent loop. We will either adopt it or copy its plugin model. That decision comes in a later ADR, after a deep-dive.
5. **Security levels.** Every tool action carries a risk level, and orgs/bots get a security level that decides what runs automatically and what needs approval (for example: read-only → ask before writing → autonomous inside limits).
6. **Approval system: basic first.** v1 ships a simple approvals flow: the bot pauses, a human sees what it wants to do, and approves, denies or edits it. Advanced policies (rules, spending limits, multiple approvers) come later, on top of the same model.

## Consequences

- The core knows nothing about Gmail specifically. It only talks to the plugin interface.
- Risk levels live in plugin manifests, so the approval engine can work out the policy without per-integration code.
