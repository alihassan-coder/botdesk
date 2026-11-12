# BotDesk Docs

BotDesk is an open-source (MIT) team of always-on AI bots that work in your apps, talk with you in chat, and ask before anything risky. Its flows are inspired by [Grok Bot](https://x.ai/news/introducing-grok-bot).

**New here?** Read in this order:

1. [getting-started.md](getting-started.md): run it on your machine
2. [product/spec.md](product/spec.md): what we're building and why
3. [architecture/agents-and-plugins.md](architecture/agents-and-plugins.md): how it works, with diagrams
4. [../CONTRIBUTING.md](../CONTRIBUTING.md): how to send your first change

## For contributors

| Doc | What it covers |
|---|---|
| [getting-started.md](getting-started.md) | Install the tools, run the web app and API, fix common problems |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Ways to help, branches, commit messages, code style, tests |
| [../SECURITY.md](../SECURITY.md) | How to report a security problem privately |
| [../CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | How we treat each other |

## Product

| Doc | What it covers |
|---|---|
| [product/spec.md](product/spec.md) | **Start here.** v1 scope, screens, build order, current status |
| [product/vision.md](product/vision.md) | Why BotDesk exists and how it wins |
| [PROGRESS.md](PROGRESS.md) | What has been built so far, newest first |
| [../GLOSSARY.md](../GLOSSARY.md) | Domain terms. Use these words in code and UI |

## Architecture and decisions

| Doc | What it covers |
|---|---|
| [architecture/high-level.md](architecture/high-level.md) | API, agent runtime, computers, plugins, data model, security levels, approvals, open owner questions (§16) |
| [architecture/agents-and-plugins.md](architecture/agents-and-plugins.md) | **Start here for bots and plugins:** how a run works, the tool pipeline, approvals, triggers, memory and the plugin platform, with diagrams |
| [adr/0001-product-scope-and-deployment.md](adr/0001-product-scope-and-deployment.md) | ADR 0001: product scope and deployment |
| [adr/0002-grok-bot-parity-and-plugin-platform.md](adr/0002-grok-bot-parity-and-plugin-platform.md) | ADR 0002: Grok Bot parity, plugin integrations, security levels, approvals |
| [adr/0003-python-backend.md](adr/0003-python-backend.md) | ADR 0003: Python backend (FastAPI, SQLAlchemy, Alembic, LangGraph, mem0) |
| [backend/README.md](backend/README.md) | Backend guide: run it, folders, request flow, routes, security |

## Building

| Doc | What it covers |
|---|---|
| [frontend/README.md](frontend/README.md) | How `apps/web` is built: folders, routes, sign-in, layout, code rules, tests |
| [../README.md](../README.md) | Repo layout and commands |
| [../AGENTS.md](../AGENTS.md) | Rules for coding agents |

## Design

| Doc | What it covers |
|---|---|
| [design/README.md](design/README.md) | Order of design work and rules |
| [design/logo/README.md](design/logo/README.md) | The logo (v7, the always-on bd): files, usage, how it was chosen |

## Research

| Doc | What it covers |
|---|---|
| [research/grok-bot-teardown.md](research/grok-bot-teardown.md) | Grok Bot UI, screen by screen, mapped to shadcn/assistant-ui |
| [research/competitors.md](research/competitors.md) | Grok Bot vs OpenAI dots, Meta Muse, Claude Tag and open-source projects |
