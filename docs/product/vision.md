# BotDesk — Product Vision

> Status: draft, 2026-11-11. Architecture is under discussion.

## What BotDesk is

BotDesk is an open-source (MIT) version of **Grok Bot**
([xAI/SpaceXSI launch, 2026-08-11](https://x.ai/news/introducing-grok-bot)): **a team of always-on AI agents
that work like colleagues.**

You message a bot the way you'd message a teammate and hand it work. Nobody has to build workflows first.
Each bot has its **own cloud computer**, signs into the tools you already use, works through multi-step jobs
while you're away, and only comes back when it needs your **approval**.

## Core concepts (from Grok Bot)

| Concept | What it means |
|---|---|
| **Bot** | An AI teammate with a role, instructions, model, tools, memory and its own computer |
| **Cloud computer** | A persistent sandbox (browser + desktop) per bot, so it can use websites and apps that have no API |
| **Jobs** | Multi-step work the bot runs in the background, which survives the user closing the app |
| **Approvals** | The bot pauses and asks a human for judgment calls (send this email? pay this invoice?) |
| **Threads and group chats** | Humans and bots in one conversation. Bots pass work, assign ownership, and @mention each other |
| **Chief of staff** | One orchestrator bot that delegates to specialist bots (inbox, expenses, recruiting, bug fixing, ops) |
| **Memory** | Bots remember conversations and how you like things done |
| **Routines ("follow along")** | The bot watches you do a job, saves the steps, takes corrections, then runs it alone |
| **Proactive** | Bots follow up on dropped threads and nudge stalled handoffs |
| **Marketplace** | Ready-made bot templates |
| **Usage** | Bots meter their own usage, separately |

Grok Bot ships as macOS and iOS apps with the same thread on every device. BotDesk starts with the web.

## Decisions so far

| Area | Decision |
|---|---|
| Name | BotDesk |
| License | MIT |
| Inspiration | Grok Bot: its concepts and mood. Original branding, no Grok/xAI trademarks or assets. |
| Build order | **1. Web (Next.js)** → 2. Desktop (Electron) → 3. Mobile (Expo) |
| Deployment | Self-hosted **and** hosted SaaS, multi-tenant from day one ([ADR 0001](../decisions/0001-product-scope-and-deployment.md)) |
| Teams | Orgs, members, roles, bots in a team, @mentions of people and bots |
| Backend | Node.js + PostgreSQL + Drizzle migrations, one API for all clients |
| Models | All major providers + custom OpenAI-compatible ones. Users bring their own keys and orgs can set keys too |
| Memory | mem0 open-source SDK on pgvector |
| UI | Prebuilt wherever possible: shadcn/ui, assistant-ui |
