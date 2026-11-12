# BotDesk web frontend

How the UI in `apps/web` is built. Read this before adding a screen. Decisions here were agreed with the owner; change them by asking first.

## The idea in one picture

```
URL ─► src/app/            routes only: each page renders one feature screen
          │
          ▼
       src/features/       everything about one feature lives in one folder
          │  read data with hooks, change it with actions
          ▼
       src/data/store.ts   the ONLY door to data (hooks + actions), including sign-in
          │  API mode: auth + org + members from apps/api; the rest still mock
          ├──────────────► src/data/api/   typed fetch client for apps/api (only store.ts uses it)
          ▼
       src/data/mock/      fake bots, threads, messages… (deleted when the API covers them)
       src/data/types.ts   the shape of everything (Bot, Thread, Message, Approval…)
```

Screens never know where data comes from. The backend is Python (FastAPI): see [docs/backend](../backend/README.md) and ADR 0003.

## Folders

| Folder | What goes there |
|---|---|
| `src/app/` | Routes. Thin: a page imports a screen from `features/` and renders it. `(app)/` holds signed-in pages inside the app shell; `(auth)/` holds sign-in pages without it. |
| `src/features/auth/` | Sign in, sign up, forgot password: the auth layout, password field, and the redirect for people already signed in. |
| `src/features/shell/` | The frame of the app: auth gate, sidebar (collapses to an icon rail), workspace header (logo tile, org switcher, "+"), user menu (sign out), logo. |
| `src/features/threads/` | A conversation: header, message list, composer, details pane. |
| `src/features/messages/` | The cards inside a message (text, reasoning, work log, computer task, question, routine created, file, handoff). |
| `src/features/approvals/` | The approval card, the approvals inbox, risk labels. |
| `src/features/bots/` | Bot avatar and status, security levels and what each allows, the create-bot screen. |
| `src/features/marketplace/` | Templates you can hire. |
| `src/features/routines/` | The routines page and the create-routine screen (schedule picker, steps editor). |
| `src/features/apps/` | Connect apps: connections, catalog, connect dialog. |
| `src/features/settings/` | Settings shell, section nav and the sections: profile, organization, appearance (theme, accent presets or a custom colour), models & keys, security, members, usage & budgets, memory. |
| `src/features/command-palette/` | ⌘K / Ctrl+K: jump to a bot, group or page. |
| `src/components/ui/` | shadcn components. Add with `pnpm dlx shadcn@latest add <name>`; don't edit by hand. |
| `src/components/` | App-wide providers (theme, tooltips, toasts). |
| `src/lib/` | Small pure helpers (formatting, @mention parsing, handles, schedules, colour contrast), each with a test. |
| `src/hooks/` | Small React hooks shared by features (current time, remembered state, phone check). |
| `src/data/` | Types, store, mock. |

## Routes

| URL | Screen |
|---|---|
| `/` | Phone: the bot list. Tablet/desktop: opens your most recent chat. |
| `/chat/[threadId]` | A conversation, DM or group. The details pane opens beside it. |
| `/bots/new` | Create a bot: from scratch or a template, with a live preview. |
| `/marketplace` | Hire a ready-made bot. |
| `/approvals` | Every request waiting for a yes, and past decisions. |
| `/routines` | Repeating jobs: schedule, last run, steps, on/off. |
| `/routines/new` | Create a routine: pick a bot, a schedule and the steps. The bot confirms in its chat. |
| `/apps` | Connected accounts, apps to connect, what each lets bots do and its risk. |
| `/settings/<section>` | `profile`, `organization`, `appearance`, `models`, `security`, `members`, `usage`, `memory`. `/settings` opens Profile. The section nav stays in view as you scroll. |
| `/sign-in` | Sign in with email and password. Returns you to `?next=` afterwards. |
| `/sign-up` | Create an account. |
| `/forgot-password` | Ask for a reset link (shows a "check your email" message; no emails are sent yet). |
| `/invite/[token]` | Accept an invite link from Settings → Members. Signed out, it offers sign in / create account and comes back. |

## Talking to the API

One setting picks where data comes from: `NEXT_PUBLIC_API_URL` in `apps/web/.env.local` (copy `.env.example`).

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000   # run the API with `pnpm dev:api`
```

| | Set (API mode) | Not set (demo / mock mode) |
|---|---|---|
| Sign in, sign up, sign out, forgot password | Real, on the API. Session is an httpOnly cookie (`botdesk_session`). | Mock. Session in `localStorage` (`botdesk.session`). Demo login `ali@acme.dev` / `botdesk123`. |
| Organization (name, address, plan) | Real. Your first organization is the current one (no switcher yet). | Mock "Acme". |
| Members, roles, remove | Real. | Mock people. |
| Invites | Real: creates a one-time link to copy (no emails yet); pending invites can be revoked. | The person joins at once. |
| Bots, threads, messages, approvals, routines, apps, keys, usage, memory | **Still mock**, even for real accounts. | Mock. |

- `src/data/api/client.ts` is the fetch wrapper: sends the cookie (`credentials: "include"`) and turns `{detail}` errors (and 422 lists) into an `ApiError` whose message screens show as is.
- `src/data/api/botdesk.ts` lists every route the web app calls; `map.ts` turns API shapes into `types.ts` shapes.
- Store actions that can fail return `{ ok: true } | { ok: false, error }` and are async in both modes.
- **Tests and e2e always run in mock mode.** Vitest doesn't load `.env.local`, and the Playwright web server sets `NEXT_PUBLIC_API_URL` to empty for its build. Don't set it there.
- Every page under `(app)/` sits behind `AuthGate` (`features/shell/auth-gate.tsx`). If there is no session, it sends you to `/sign-in?next=<where you were>`.

## Layout by screen size

| Size | Layout |
|---|---|
| Phone, under 768px | One thing at a time. Bot list is home; a chat is full screen with a back button; details slide up as a sheet. |
| Tablet, 768–1279px | Sidebar + chat. Details slide in from the right. |
| Desktop, 1280px+ | Sidebar + chat + details pane (resizable, can be closed; the app remembers). |

On tablet and desktop the sidebar collapses to an icon rail. The app remembers the choice in `localStorage` (`botdesk.sidebar.open`).

## Look

Light by default, dark mode from day one (toggle in the user menu). Black and white with one accent, ultramarine `#3B30FF` by default, plus status colours: amber = working, ultramarine = needs your approval, red = error, grey = sleeping. Geist font. Messenger-style chat: your messages on the right in a dark bubble, bot messages on the left in light grey, cards full width under the bot's message.

Members can change the accent in Settings → Appearance: a preset or any custom colour. Text on the accent switches between black and white to stay readable (`src/lib/color.ts`). The choice is saved in this browser (`botdesk.accent`).

## House rules for code

- One component per file, under ~150 lines. If it grows, split it.
- Names come from [GLOSSARY.md](../../GLOSSARY.md): `ApprovalCard`, `Bot`, `Thread`, never synonyms.
- Comments say *why*, not *what*. Plain words, no clever abstractions.
- Server components by default; `"use client"` only for interaction or store reads.
- Every screen handles empty and not-found states.
- Times like "2m ago" are computed in the browser only (`useNow`), so server and browser HTML match.
- Logic lives in `src/lib/` or the store, with tests. Every new feature comes with tests in the layers below.

## Tests

Three layers, cheapest first. Add to each when you add a feature.

| Layer | Where | Tools | Run |
|---|---|---|---|
| Logic | `src/lib/*.test.ts`, `src/data/store.test.ts` | Vitest | `pnpm test:web` |
| UI components | `src/features/**/*.test.tsx` | Vitest + Testing Library in jsdom: render, click and type like a user | `pnpm test:web` |
| Whole app | `e2e/*.spec.ts` | Playwright in your installed Chrome, 1440px desktop and phone (Pixel 7) | `pnpm test:e2e` |

- Test setup (browser stubs, fresh mock data after every test) is in `src/test/setup.ts`; render helper in `src/test/render.tsx`.
- Find elements the way a person would: by role and visible text (`getByRole("button", { name: "Approve" })`), not by CSS class.
- E2E tests import `test` from `e2e/fixtures.ts`, which signs in the demo user before the page loads. Auth tests (`auth.desktop.spec.ts`) use Playwright's plain `test`, so they start signed out.
- Files ending in `desktop.spec.ts` run in the desktop project; `phone.spec.ts` runs in the phone project.
- E2E builds the app and serves the production build on :3200, so it never clashes with `pnpm dev:web` on :3000 (change the port with `E2E_PORT`). The first run takes ~1–2 minutes because of the build.

Run everything from the repo root:

```bash
pnpm test:web      # logic + UI component tests, ~10s
pnpm test:e2e      # build, then Playwright on :3200
pnpm check         # typecheck + lint + unit tests, before pushing
```

Inside `apps/web`, `pnpm test:watch` re-runs Vitest as you edit.

## Build order

1. **Slice 1 (done):** app shell, DM thread with all message cards and a working composer, inline approval card (Approve / Deny / Edit).
2. **App pages (done):** create bot, marketplace, approvals inbox, routines, connect apps, settings, ⌘K palette, workspace header.
3. **Accounts and polish (done):** mock sign in / sign up / forgot password with an auth gate, create routine, manage organization, collapsible sidebar, custom accent.
4. **Wire to the API (in progress):** auth, organization, members and invites are on the API. Next: bots, threads and streaming bot replies, then an org switcher.
5. **Later:** group chats with an @mention picker; then computer view (live screen, take over) and routine recording.

Each slice is shown to the owner before the next starts.
