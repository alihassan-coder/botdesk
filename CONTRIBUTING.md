# Contributing to BotDesk

Thanks for wanting to help! This guide covers everything from your first question to your merged pull request. If anything here is unclear, that's a bug in the docs: please tell us.

**Contact:** questions you'd rather not ask in public can go to **alihassan.coder@gmail.com**.

## Ways to help

You don't need to write code to make a difference:

- **Report a bug.** [Open an issue](../../issues/new/choose) with steps to reproduce it.
- **Suggest an idea.** Open a feature request and describe the problem it solves.
- **Improve the docs.** If something confused you, fixing it helps the next person.
- **Design.** Feedback on screens, flows and wording is valuable.
- **Write code.** Pick an issue labelled `good first issue` or `help wanted`, or propose your own.

For anything bigger than a small fix, **open an issue first** so we can agree on the approach before you spend time on it.

## Set up your machine

Follow **[docs/getting-started.md](docs/getting-started.md)**. In short, you need Node.js 22+, pnpm, Python 3.13 and [uv](https://docs.astral.sh/uv/). For the full backend, you also need a Postgres database (a free [Neon](https://neon.tech) database works).

Quick check that everything works:

```bash
pnpm install
uv sync --all-packages   # every Python package (API, plugin SDK, plugins) into one .venv
pnpm check               # type checks, linting and tests for everything
```

## How we work

### Branches and pull requests

1. Fork the repo and create a branch from `main`: `git checkout -b fix/approval-card-overflow`.
2. Make your change in small, focused commits.
3. Run `pnpm check` (and `pnpm test:e2e` if you changed the web app's screens).
4. Open a pull request and fill in the template. Link the issue it fixes.
5. A maintainer reviews it. We may ask for changes; that's normal and not a judgement.

Keep pull requests small: one idea per PR is much easier to review than five.

### Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org): `type(scope): what changed`.

```
feat(api): invite people to an organization by email
fix(web): approval card text no longer overflows on phones
docs: explain how plugins are discovered
```

Sign off every commit with `git commit -s`. It adds a `Signed-off-by:` line confirming you wrote the change and can contribute it (the [Developer Certificate of Origin](https://developercertificate.org)). There's no contributor licence agreement.

Types: `feat` (new feature), `fix` (bug fix), `docs`, `test`, `refactor`, `chore`. Scopes: `web`, `api`, or leave it out.

### Code style

We care most that code is **easy for the next person to read**: plain names, small functions, and comments that explain *why*, not *what*.

| Part | Language and tools | Rules worth knowing |
|---|---|---|
| `apps/web` | TypeScript, Next.js 16, Tailwind, shadcn/ui | Screens get data only through `src/data/store.ts`. Use shadcn components before writing custom UI. See [apps/web/AGENTS.md](apps/web/AGENTS.md) and the [frontend guide](docs/frontend/README.md). |
| `apps/api` | Python 3.13, FastAPI, SQLAlchemy, Alembic | Layers go one way: routes → controllers → services → models. Every route lives under `/api/v1`. Database changes always come with an Alembic migration. See [apps/api/AGENTS.md](apps/api/AGENTS.md) and the [backend guide](docs/backend/README.md). |
| `packages/plugin-sdk`, `plugins/*` | Python 3.13, Pydantic | The SDK depends on Pydantic only. Plugins import the SDK and never the API. See [Write a plugin](#write-a-plugin). |

Formatting and linting are automatic: ESLint for the web app; ruff and mypy (strict) for every Python package. `pnpm check` runs them all.

### Tests

Every change to logic needs a test. Every bug fix needs a test that would have caught the bug.

- **Web:** Vitest + Testing Library for logic and components (`pnpm test:web`), Playwright for real browser flows (`pnpm test:e2e`).
- **API:** pytest (`pnpm test:api`). Tests use an in-memory database, so they need no setup and no network.
- **Plugin SDK and plugins:** pytest in each package (`pnpm --filter @botdesk/plugin-sdk test`, or `uv run --package botdesk-plugin-demo pytest plugins/demo` from the root).

### Write a plugin

A plugin adds tools that bots can use. It is a small Python package that depends only on the [plugin SDK](packages/plugin-sdk/README.md); the SDK README has a five-minute walkthrough. In this repo:

1. Copy `plugins/demo` to `plugins/<name>` and rename the package (`botdesk-plugin-<name>`, import `botdesk_<name>`), the entry point and the `package.json` name. The workspace picks up every folder in `plugins/`.
2. Write each tool as an `async` handler with a Pydantic args model, and pick its risk class honestly (the SDK README explains the 7 classes). Set `untrusted_output=True` for tools that return outside text.
3. Test it without the app: `validate_manifest(your_plugin())` and `botdesk_plugin_sdk.testing.call_tool(...)`. Run `uv sync --all-packages`, then `uv run --package botdesk-plugin-<name> pytest plugins/<name>`.
4. To try it in the API, add it to `apps/api/pyproject.toml` (a dependency plus a `[tool.uv.sources]` workspace line), run `uv lock`, add its id to `PLUGINS` in `apps/api/.env`, and start the API. `GET /api/v1/orgs/{id}/plugins` should list it; if not, the API log says why it was skipped.

Plugins must not import anything from `apps/api`, and a plugin that talks to an outside service needs a README saying what it reads, what it can change, and which scopes it asks for.

### Words we use

Product terms (Bot, Run, Approval, Routine, Security level…) are defined in [GLOSSARY.md](GLOSSARY.md). Please use them exactly, in code and in the UI, so everyone means the same thing.

### Big decisions

Architecture decisions are recorded as short documents in [docs/adr/](docs/adr/). To change one, propose a new ADR in a pull request rather than editing an accepted one.

## Licenses

BotDesk is [MIT licensed](LICENSE). By contributing, you agree that your contribution is released under the same license.

New dependencies must use a permissive license (MIT, Apache-2.0, BSD or ISC). Anything else needs discussion and an ADR first.

## Code of Conduct

Be kind and assume good intent. Everyone taking part follows our [Code of Conduct](CODE_OF_CONDUCT.md).

## Security issues

Don't open a public issue for a security problem. See [SECURITY.md](SECURITY.md).
