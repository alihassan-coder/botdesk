<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/design/logo/svg/wordmark-white.svg">
    <img src="docs/design/logo/svg/wordmark-ink.svg" alt="botdesk" height="56">
  </picture>
</p>

<p align="center"><strong>Your AI team, always on.</strong><br>
Bots that work in your apps, talk with you in chat, and ask before doing anything risky.</p>

<p align="center">
  <a href="LICENSE">MIT license</a> ·
  <a href="docs/getting-started.md">Get started</a> ·
  <a href="CONTRIBUTING.md">Contribute</a> ·
  <a href="docs/README.md">Docs</a>
</p>

---

## What is BotDesk?

BotDesk gives your team a set of AI **bots**, each with a job: one manages your inbox, one fixes bugs, one coordinates the others. You talk to them in chat threads, the way you'd talk to a colleague. They can work while you're away, and whenever they want to do something risky, like sending an email, spending money or deleting something, they **stop and ask you first**. You approve, edit or say no.

- **Any AI model.** Bring your own key for Anthropic, OpenAI or others.
- **Built for teams.** Organizations, roles, invites, and shared bots.
- **Safe by default.** Every bot has a security level, and risky actions wait for your approval.
- **Open source and self-hostable.** MIT licensed. Run it on your own server with your own database.

## Status

BotDesk is in **early development**. Here's what works today:

| Area | State |
|---|---|
| Web app (every screen, desktop and phone) | ✅ Built. Runs on demo data, or on the real API for the parts below |
| Accounts: sign up, sign in, sign out, profile, password | ✅ API done |
| Organizations, members, roles, invites | ✅ API done, web connected |
| Bots (create, edit, remove) | ✅ API done, web connected |
| Chats and messages (stored) | ✅ API done |
| Bots that think and reply | 🚧 Next |
| Approvals, plugins (Gmail first), memory, routines | 📋 Planned |

The full history is in [docs/PROGRESS.md](docs/PROGRESS.md), and the plan is in [docs/product/spec.md](docs/product/spec.md).

## Try it in two minutes (no backend needed)

You need [Node.js 22+](https://nodejs.org) and [pnpm](https://pnpm.io/installation).

```bash
git clone https://github.com/alihassan-coder/botdesk.git
cd botdesk
pnpm install
pnpm dev:web
```

Open http://localhost:3000 and click **Explore the demo**, or sign in with `ali@acme.dev` / `botdesk123`. Everything runs on demo data in your browser.

To run the real backend too, follow **[docs/getting-started.md](docs/getting-started.md)**.

## How the code is organised

```
botdesk/
├── apps/
│   ├── web/      Next.js web app (the first client)
│   ├── api/      Python API: FastAPI, SQLAlchemy, Alembic
│   ├── desktop/  Desktop app (later)
│   └── mobile/   Mobile app (later)
├── docs/         Product, architecture, design and decisions
└── package.json  Root commands for the whole repo (pnpm + Turborepo)
```

| Command (from the repo root) | What it does |
|---|---|
| `pnpm dev:web` | Run the web app at http://localhost:3000 |
| `pnpm dev:api` | Run the API at http://localhost:8000 (interactive docs at `/api/docs`) |
| `pnpm test:web` / `pnpm test:api` | Run the web or API tests |
| `pnpm test:e2e` | Browser tests of the web app (Playwright) |
| `pnpm check` | Type checks, linting and all tests: run this before opening a pull request |
| `pnpm db:migrate` / `pnpm db:seed` | Update the database schema / add demo data |

## Documentation

Start with **[docs/README.md](docs/README.md)**, a guided map of every document. Good first reads:

- [Getting started](docs/getting-started.md): set up everything on your machine
- [How bots think and how plugins plug in](docs/architecture/agents-and-plugins.md): the core design, with diagrams
- [Frontend guide](docs/frontend/README.md) and [Backend guide](docs/backend/README.md)
- [Glossary](GLOSSARY.md): the words we use (Bot, Run, Approval, Routine…)

## Contributing

Contributions of every size are welcome: bug reports, ideas, docs, design and code. Read **[CONTRIBUTING.md](CONTRIBUTING.md)** to get set up and see how we work. Everyone taking part follows our [Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Please **don't** report security problems in public issues. Email **alihassan.coder@gmail.com** instead. Details are in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). You can use, change and share BotDesk freely, including commercially.
