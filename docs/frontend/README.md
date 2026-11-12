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
       src/data/store.ts   the ONLY door to data (hooks + actions)
          │  today: in-memory mock with fake bot replies
          ▼
       src/data/mock/      fake bots, threads, messages… (deleted when the API lands)
       src/data/types.ts   the shape of everything (Bot, Thread, Message, Approval…)
```

When the API exists, only `store.ts` changes. No screen changes.

## Folders

| Folder | What goes there |
|---|---|
| `src/app/` | Routes. Thin: a page imports a screen from `features/` and renders it. |
| `src/features/shell/` | The frame of the app: sidebar, workspace header (logo tile, org switcher, "+"), user menu, logo. |
| `src/features/threads/` | A conversation: header, message list, composer, details pane. |
| `src/features/messages/` | The cards inside a message (text, reasoning, work log, computer task, question, routine created, file, handoff). |
| `src/features/approvals/` | The approval card, the approvals inbox, risk labels. |
| `src/features/bots/` | Bot avatar and status, security levels and what each allows, the create-bot screen. |
| `src/features/marketplace/` | Templates you can hire. |
| `src/features/routines/` | The routines page. |
| `src/features/apps/` | Connect apps: connections, catalog, connect dialog. |
| `src/features/settings/` | Settings shell and its sections: profile, appearance (theme, accent), models & keys, security, members, usage & budgets, memory. |
| `src/features/command-palette/` | ⌘K / Ctrl+K: jump to a bot, group or page. |
| `src/components/ui/` | shadcn components. Add with `pnpm dlx shadcn@latest add <name>`; don't edit by hand. |
| `src/components/` | App-wide providers (theme, tooltips, toasts). |
| `src/lib/` | Small pure helpers (formatting, @mention parsing), each with a test. |
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
| `/apps` | Connected accounts, apps to connect, what each lets bots do and its risk. |
| `/settings/<section>` | `profile`, `appearance`, `models`, `security`, `members`, `usage`, `memory`. `/settings` opens Profile. |

## Layout by screen size

| Size | Layout |
|---|---|
| Phone, under 768px | One thing at a time. Bot list is home; a chat is full screen with a back button; details slide up as a sheet. |
| Tablet, 768–1279px | Sidebar + chat. Details slide in from the right. |
| Desktop, 1280px+ | Sidebar + chat + details pane (resizable, can be closed; the app remembers). |

## Look

Light by default, dark mode from day one (toggle in the user menu). Black and white with one accent, ultramarine `#3B30FF`, plus status colours: amber = working, ultramarine = needs your approval, red = error, grey = sleeping. Geist font. Messenger-style chat: your messages on the right in a dark bubble, bot messages on the left in light grey, cards full width under the bot's message.

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
| Whole app | `e2e/desktop.spec.ts`, `e2e/phone.spec.ts` | Playwright in your installed Chrome, 1440px desktop and phone | `pnpm test:e2e` |

- Test setup (browser stubs, fresh mock data after every test) is in `src/test/setup.ts`; render helper in `src/test/render.tsx`.
- Find elements the way a person would: by role and visible text (`getByRole("button", { name: "Approve" })`), not by CSS class.
- E2E builds the app and serves the production build on :3200, so it never clashes with `pnpm dev:web` on :3000 (change the port with `E2E_PORT`). The first run takes ~1–2 minutes because of the build.

## Build order

1. **Slice 1 (done):** app shell, DM thread with all message cards and a working composer, inline approval card (Approve / Deny / Edit).
2. **App pages (done):** create bot, marketplace, approvals inbox, routines, connect apps, settings (7 sections), ⌘K palette, workspace header.
3. **Next:** group chats with an @mention picker; then computer view (live screen, take over) and routine recording.

Each slice is shown to the owner before the next starts.
