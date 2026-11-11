# BotDesk — Vision

## What

BotDesk is an open-source (MIT) version of **Grok Bot**
([xAI launch, 2026-08-11](https://x.ai/news/introducing-grok-bot)): **a team of always-on AI bots that work like colleagues.**

You message a bot like a teammate and hand it work, with no workflows to build first. Each bot has its own
computer, signs into your tools, works through multi-step jobs while you're away, talks with you and other
bots in threads, and comes back when it needs your approval. Terms: [GLOSSARY.md](../../GLOSSARY.md).
Scope and screens: [spec.md](spec.md).

## Why open source wins

Grok Bot, OpenAI dots and Meta Muse are closed, cloud-only and tied to one model vendor
([competitors](../research/competitors.md)). BotDesk's edge:

1. **Own it.** MIT, self-hostable, or use the hosted SaaS. Multi-tenant teams from day one.
2. **Any model.** Every major provider or a custom endpoint; member keys and org keys.
3. **Safe by design.** One computer per bot, risk-classed tools, security levels, and an approvals inbox.
4. **Transparent.** Memory you can see and edit; cost per bot and per run; budgets that pause a bot.
5. **Extensible.** Integrations are plugins with a manifest, so adding the 100th is as easy as the first.

## Principles

- Match Grok Bot's flows; keep BotDesk's own identity (no Grok/xAI assets).
- Prebuilt libraries for everything that isn't the core experience.
- Web first; desktop and mobile reuse the same API.
