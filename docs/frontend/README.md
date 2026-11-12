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
| `src/features/shell/` | The frame of the app: sidebar, user menu, logo, placeholder screens. |
| `src/features/threads/` | A conversation: header, message list, composer, details pane. |
| `src/features/messages/` | The cards inside a message (text, reasoning, work log, computer task, question, routine created, file, handoff). |
| `src/features/approvals/` | The approval card (and later the approvals inbox). |
| `src/features/bots/` | Bot avatar and status. |
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
| `/approvals`, `/routines`, `/apps`, `/marketplace`, `/settings` | Coming in later slices (placeholder for now). |

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
- Logic lives in `src/lib/` and is tested with Vitest (`pnpm --filter @botdesk/web test`). Screens are checked in a real browser at phone, tablet and desktop sizes.

## Build order

1. **Slice 1 (now):** app shell, DM thread with all message cards and a working composer, inline approval card (Approve / Deny / Edit).
2. Group chats with @mentions.
3. Approvals inbox.
4. Details pane tabs in depth (routines, memory, computer).
5. Routines, Connect apps, Marketplace, Settings, ⌘K command palette, one at a time.

Each slice is shown to the owner before the next starts.
