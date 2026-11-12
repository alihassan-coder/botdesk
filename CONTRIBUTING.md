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
cd apps/api && uv sync && cd ../..
pnpm check          # type checks, linting and tests for web and API
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

Formatting and linting are automatic: ESLint for the web app; ruff and mypy (strict) for the API. `pnpm check` runs them all.

### Tests

Every change to logic needs a test. Every bug fix needs a test that would have caught the bug.

- **Web:** Vitest + Testing Library for logic and components (`pnpm test:web`), Playwright for real browser flows (`pnpm test:e2e`).
- **API:** pytest (`pnpm test:api`). Tests use an in-memory database, so they need no setup and no network.

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
