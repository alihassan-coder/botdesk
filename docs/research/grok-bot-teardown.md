# Grok Bot — UI/UX Teardown (reference for BotDesk)

> Status: research note, 2026-11-11. Target is **Grok Bot** (x.ai/bot, launched 2026-08-11): a desktop + iOS app of "always-on AI agent teammates". Appendix A has notes on grok.com chat.
> **Method:** We used the BrowserOS neo agent browser on public pages only: x.ai/bot, the launch post, Marketplace, Guides, Changelog (v0.79.3, Nov 6 2026) and docs.x.ai/grok-bot/*. Screenshots are in `grok-screens/`. A small amount of web search filled gaps. We did **not** install Grok Bot, sign up, or download the app. So every in-app observation comes from xAI's own marketing mock-ups, guide screenshots, docs and changelog text. Treat pixel values as estimates.
> **Branding rule:** BotDesk copies patterns, not assets. That means no Grok/xAI names, no blob-character mascot, no logo, and no copied illustrations.

---

## 0. TL;DR — what Grok Bot actually is (UX-wise)

- **The interface is a messenger.** The shell looks like iMessage or Slack: a list of bots on the left, a conversation in the middle, and a details pane on the right. Bots are "teammates" with avatars, names, titles, unread dots and last-message previews.
- **The bot has a computer, and the UI shows it.** Each conversation has a live **computer preview** (thumbnail → full screen, "Watching" → "Take control").
- **Work shows up as cards in the transcript.** Computer-task cards, approval cards, question cards with options, draft cards (email/Slack), routine-created lines, Page cards, shopping/order cards and call cards. Cards carry most of the product's value. Plain text bubbles are short.
- **Approvals happen in the chat.** The docs say outright that there is no separate approvals inbox. Approval cards appear in the bot's chat and in desktop/phone notifications. An "Auto-review" agent decides which actions need a card.
- **Each bot has a details pane** with tabs for Media/Library, Computer, Routines and Details (name, title, description, notifications).

---

## 1. Information architecture

```
App window (desktop: macOS/Windows/Linux; iOS app syncs same state)
├─ Sidebar (280px)
│  ├─ traffic lights + [+] menu → New Bot · New Channel / New group chat
│  ├─ Search (⌘⇧F bots; ⌘K palette for messages/files/actions)
│  ├─ (newer) Pinned bots as avatar tiles grid
│  ├─ Bot rows: avatar · name · time · 1-line preview · unread dot
│  ├─ User-made Sections ("Cursor", "Ops", "Projects", "Unassigned") — right-click "Move to new section"
│  ├─ Group chats / channels (stacked multi-avatar)
│  ├─ Hidden Bots (collapsible, count) → "Show in sidebar"
│  └─ Footer: Plugins / Connect apps · user avatar+name → account menu
│        (Get Grok Bot for iOS · Settings · About · Help Center · Send Feedback · Log out)
├─ Conversation (DM with one bot, or group chat 2–6 bots + you)
│  ├─ Header: bot avatar + name (click → details) · computer icon · settings · »collapse pane
│  ├─ Transcript: bubbles + cards + system lines ("Renamed to…", "Created routine ⏱ …", "Messages from A and B")
│  └─ Composer: [+] attach · "Message <Bot>" · mic (dictation) / waveform (voice chat when empty)
├─ Right pane (Bot details; ⌘⇧I / ⌘⌥B)
│  ├─ Profile (avatar, editable name, title/label, description) → Settings view
│  ├─ Computer preview ("<Bot>'s screen") → full-screen live view
│  ├─ Routines list (+) → Routine detail (Active toggle, Delete, Test run, Name, Instruction, When to run, Run history)
│  ├─ Library tab: Pinned · All · Pages · Media · Links · Files · Apps (Today / This week / Older)
│  └─ Tasks pane: cloud agents a bot started (Working / Run failed / Status unavailable)
├─ Page view (bot-built report/dashboard fills window; chat shrinks to side panel "Message about…")
├─ Connect apps (plugins/MCP catalog, custom connector, Bot templates gallery, Email address)
├─ Settings: General (Bot → Auto-review + Custom Rules; Agent rules; Security key) · Computer · Vault
│  (Logins, Payments, Contact info) · Appearance · Notifications · Usage & Billing · Language · Import Memory
└─ Command palette (⌘K), shortcuts sheet (⌘/), full-screen media viewer
Web (x.ai): Marketplace (categories, search, Featured, bot detail → "Import Bot"), Guides, Use cases, Changelog
```

### Screen-by-screen

| Area | What we observed | Source |
|---|---|---|
| **Bot list / team roster** | Sidebar rows: 36px round avatar, name 14px, timestamp right, 1-line grey preview ("sent. inbox at zero, 5 drafts parked…"). Red unread dot on the avatar. The active row has a soft grey fill (`rgba(10,10,10,.055)`, radius 10). User-made sections. A collapsible "Hidden Bots (4)" section. Sidebar adapts to the number of bots: 1 bot = hidden behind a toggle, 2–4 = narrow rail, 5+ = full list. ⌘1–9 jumps to a bot. On Mac, "View Unread" filters the list. | 13-*, 15-*, changelog |
| **Primary bot / "chief of staff"** | Onboarding shows "Introducing your primary Bot" (create one, or choose an existing bot). The primary bot routes work to the others. | docs/bots |
| **DM with a bot** | iMessage-style transcript. Bot messages are left-aligned grey bubbles, user messages are right-aligned near-black pills. Timestamps are centred and grey ("10:40 PM", "Today 1:45 PM"). Reactions sit on the bubble (a 👍 badge in the corner). Reply-to and threads exist. | 13-*, docs |
| **Group chats** | ⌘⇧N or "New chat" with a "To:" field (2–6 bots). The avatar is a stacked cluster. Bots @mention each other and you, and @everyone works. A "Messages from **A** and **B**" separator shows bot-to-bot hand-offs. Approvals, secret requests and drafts are **not** shown in groups. | 13-*, docs/chat |
| **Channels (projects)** | The "+" menu offers **New Bot / # New Channel**. A channel has a **Members** roster in the right pane (avatar + name rows, "+ Add Member"). | 16-* |
| **Threads** | You can thread on a single result or approval. Bots share context across threads. Slack threads are a first-class surface for Team Bots. | docs, changelog |
| **Approvals** | **Inline cards** in the DM. They state the action in one sentence, show the app logo, and flag irreversible changes ("This can't be undone"). Buttons: *Allow once / Always allow / Deny*. Terminal commands get *Allow / Skip + Manage settings*. Cards expire after 30 minutes for background work and then read "Expired". Rules (*Ask first / Allow automatically*) live in Settings → General → Bot. **There is no central inbox.** Desktop/phone notifications and sidebar unread dots do that job. | docs/approvals, changelog |
| **Question cards** | Card with a prompt ("Want me to send that to Lilet? I won't send anything until you pick."), a list of options (Send that reply / Hold off / Also DM the $215 Express), a close ×, and a collapsed "Tweak ✓" state once answered. | 15-multi-bot-chain, 15-bot-settings |
| **Computer (live view)** | Inline "Computer" card: title, task line ("Sign in to Salesforce so I can see the accounts you own"), status pill (*Working* in amber with a spinner, *Done* in green), and a live screenshot thumbnail on a gradient backdrop. The right pane shows a "<Bot>'s screen" preview. Full screen opens in **Watching** mode until you press **Take control**. Hand-back flow: "Take over" → "I'm done". Lifecycle states: *Asleep / Waking up… / Reconnecting / Couldn't Reach … Computer*. Screen is 1920×1200. | 13-c, 15-*, docs/computer, changelog |
| **Work log** | A compact checklist bubble ("✓ **Salesforce** → list pulled · 52 accounts", "✓ **Hex** → 3 lookalike segments"). Tool name in bold, result after an arrow. | 13-a |
| **Task / cloud-agent card** | "Build apps/shader-lab preset-swapper" with a blue **Running** pill and an "Open in Cursor" button. The PR status updates when the PR merges. | 15-bot-settings |
| **Routines** | System line "Created routine ⏱ Overnight outbound". Routine detail pane fields: Active toggle, Delete, **Test run**, Name, Instruction (text area), When to run ("On weekdays at 9:00 AM", "+ Add another"), Run history (dated rows with ✓). Triggers are written in words (Slack mention, Linear issue, webhook with POST URL/key/header). | 15-routines-triggers, docs/routines |
| **"Follow along" / Teach a task** | A floating recording bar: "**Weekly Reporting** is watching and learning · 0:04 · **Teach a task**", with a cursor labelled "You" over the shared screen. It records up to 10 minutes and turns the recording into a draft skill for you to review. | 10-part3, docs/skills |
| **Memory** | System line "Updated memory for ● Account Manager" (a coloured bot chip). "Import Memory" in Settings brings in context from another assistant. | 10-part3, changelog |
| **Bot setup / settings** | Right pane "Settings": large avatar, Name, Title ("Describe what your Bot does"), Description (long text area), Notifications toggle. Avatar picker tabs: *Bot (shape+colour) / Generate / Upload*. Create dialog: name + shape + colour → Create. | 15-bot-settings, docs/bots |
| **Library & Pages** | The Library has filter chips: Pinned/All/Pages/Media/Links/Files/Apps. A Page is a bot-built doc or dashboard. It opens full window with the chat docked on the side ("Message about…"). Share options: Only you / Team / Anyone with link (pages.grok.bot). | docs/files, changelog |
| **Vault** | Settings → Vault, with tabs for Logins, Payments and Contact info. Secure Forms keep secrets masked and out of the model's view. | docs, changelog |
| **Marketplace** | On the web: H1 "Marketplace", pill category filters (All, From Grok Bot Team, Engineering, Sales…), a full-width rounded search field, a Featured grid of 4 cards (big coloured blob avatar + creator photo badge, name tinted in the avatar colour), category rows with "View all", and "Add" per bot. Bot detail page: avatar, H1, "By <creator>", description, black pill **Import Bot**, then the instructions. In-app equivalent: Connect apps → Bot templates → Import Bot. | 11, 14 |
| **Usage** | Usage & Billing shows a meter and chart, a "Top up your balance → Purchase Credits" flow, usage-limit cards in the chat, and a banner. A breakdown per bot exists. Plans: Premium $30 / Super $100 / Ultra $200 per month. | changelog, 10-part4 |
| **Voice** | Dictation (⌘D) and a voice-chat waveform button (shown when the composer is empty). There are in-call controls, and a "Voice chat" transcript card afterwards. Bots can also place phone calls (call cards with Take over). | docs/chat |

---

## 2. Layout

| Fact | Value |
|---|---|
| Shell | 3 panes: **sidebar 280px**, flexible conversation, **right details pane ≈ 300–340px** (collapsible with »). Desktop window chrome is native: traffic lights sit inside the sidebar. |
| Sidebar | Translucent light grey (`rgba(251,251,251,.35)` over the vibrancy layer). Search field 32px tall, radius 10. Rows 53px with 8px padding and radius 10. |
| Conversation header | ~44px tall: avatar 16–20px + bot name 14px on the left; computer icon / settings / collapse on the right. A hairline border sits underneath. |
| Message column | Bot bubbles max ≈ 560px wide. User bubbles are right-aligned. No centred "reading column": the transcript is a messenger, not a document. |
| Composer | Pinned to the bottom. Full-width rounded pill, ~40px tall, radius ~20, 1px border. "+" on the left, placeholder "Message <Bot name>", circular mic on the right. Grows for multi-line input. |
| Empty state | A new bot opens straight into a chat where the bot introduces itself ("Hey Armand, good to meet you. What do you want me around for?"). The bot talks first; there's no blank hero. |
| iOS | Same model in a single-column stack: bot list → chat → profile sheet (Library, Routines, Edit). Group creation is "+ → New Group Chat". The avatar menu (top left) leads to Connect apps and Settings. Routine rows can be swiped to delete. |

---

## 3. Visual language

**The app is light-first:** every official mock-up is light. Dark mode exists (changelog: "In dark mode, Purchase Credits…", "Switch to dark theme"). The style is soft, warm-neutral, Apple-ish and low-contrast, with colour coming almost entirely from bot avatars and status pills.

| Token | Light (measured from mock-ups) | Dark (est., from grok.com tokens) |
|---|---|---|
| App background | `#FFFFFF` / `#FBFBFA` | `#131211` |
| Sidebar | `#F7F7F5` translucent | `#181716` |
| Bot bubble / card fill | `rgba(16,16,0,.04)` ≈ `#F4F4F1` | `rgba(255,255,255,.06)` ≈ `#232220` |
| User bubble | `#111110` bg, `#FFFFFF` text | `#E6E5E3` bg, `#111` text |
| Active row / hover | `rgba(10,10,10,.055)` | `rgba(255,255,255,.06)` |
| Border / hairline | `rgba(20,20,20,.15)` on inputs; `#E6E5E3` dividers | `#383836` |
| Text primary / secondary / tertiary | `#141414` / 60% / 40% (`rgba(20,20,20,.6/.4)`) | `#E6E5E3` / 65% / 47% |
| Status: working | amber pill (`#F5A524`-ish text on 12% tint) | same hue |
| Status: done / success | green pill (`#05A95F` on 14% tint) | `#00C972` |
| Status: running (agent) | blue pill (`#1084FE`) | same |
| Danger | `#FF263C` | same |
| Bot identity colours | teal `#4FB3A5`, orange `#F59A3C`, violet `#8B5CF6`, blue `#3B82F6`, pink `#FF5FAF`, red `#FF4D4F` | same |

- **Typography:** the app mock uses `system-ui` (SF on Mac). Body is 14/20 in bubbles, 13/16 for system lines, 12/16 for previews. In Oct 2026 the app got "a new typeface for text and code". The x.ai site uses a geometric grotesk; grok.com uses `universalSans`/"X-VF". BotDesk should use **Inter or Geist** (both open source).
- **Radius:** bubbles and cards 16, rows and inputs 10, pills and buttons fully round, window 16–20, marketing cards 24–28.
- **Shadows:** almost none inside the app. Only the window and menus get a soft elevation (`0 4px 16px rgba(0,0,0,.1)`). Cards are flat fills, not outlined.
- **Iconography:** thin 1.5px outline icons (Lucide-like), 16px. Status icons are tiny (spinner, check dot).
- **Avatars:** a signature "blob character": a coloured shape with two pill eyes. It comes in shapes (round, droplet, squircle, pumpkin) and one colour per bot. BotDesk needs its **own** avatar system, e.g. generated geometric glyphs or monogram shapes with a per-bot hue.
- **Motion:** emoji reactions "pop" into place. Status lines appear right after send (generic "Thinking" is delayed so it doesn't flash). Images fade in. Sidebar and panes slide. Hero-mock messages stream in one at a time. Durations are ~120ms (fast) to 320ms (slow), with ease-out-quint `cubic-bezier(.23,1,.32,1)` (taken from grok.com tokens).

---

## 4. Component → shadcn/ui / assistant-ui mapping

| Grok Bot component | BotDesk building block | Customisation needed |
|---|---|---|
| App shell, 3 panes | shadcn **Sidebar** (`collapsible="icon"`) + **Resizable** panels | A right inset panel. Auto mode by bot count (hidden/rail/full). Mac traffic-light inset in Electron. |
| Bot list rows | shadcn `SidebarMenuButton` + **Avatar** + **Badge** | Two-line row (name/time + preview), unread dot on the avatar, stacked avatar for groups. |
| Sections, Hidden bots | `SidebarGroup` + **Collapsible** + **ContextMenu** | Right-click Move to section / Pin / Hide / Rename / Delete. Drag-and-drop with dnd-kit. |
| "+" New Bot / New Channel | **DropdownMenu** + **Dialog** | Create dialog: name, avatar shape and colour. |
| ⌘K palette, ⌘/ shortcuts sheet | **Command** (cmdk) + **Dialog** | Index bots, messages, files and plugins. Use a hotkey lib. |
| Transcript | assistant-ui **Thread** / `ThreadPrimitive.Viewport` | Bubble skin (user dark pill right, bot grey left), timestamp separators, system lines. For **multi-author group chats**, put the author in message metadata and render a custom author avatar/name. assistant-ui assumes a single assistant, so use `ExternalStoreRuntime`. |
| Composer | assistant-ui **Composer** + **Attachment** primitives | Pill shape, "Message <Bot>" placeholder, @mention popover (custom, using **Popover**+**Command**), mic/voice button swap when empty. |
| Approval card | assistant-ui **Tool UI** (`makeAssistantToolUI`, human-in-the-loop `addResult`) + shadcn **Card**/**Button** | Allow once / Always allow / Deny, risk flag, app logo, expiry countdown, "Expired" state. |
| Question card (options) | Tool UI + **RadioGroup**/button list | Answered state collapses to "✓ choice". |
| Computer card + live view | Tool UI + Card + **Badge** status pill. Full screen in **Dialog**/**Sheet** with a noVNC-based viewer (e.g. `react-vnc`) | Watching ↔ Take control toggle, "I'm done", Asleep/Waking states. |
| Work-log checklist | assistant-ui **ToolGroup**/fallback tool UI | One-line rows: ✓ **Tool** → result. Collapsible. |
| Reasoning / status line | assistant-ui **Reasoning** / custom status in `MessagePrimitive` | A short live phrase ("Pulling Salesforce list…"), delayed for generic phrases. |
| Draft card (email/Slack) | Tool UI + Card | Recipients, body preview, Send / Discard, "Needs approval". |
| Routine line + routine pane | Custom message part. Pane uses **Switch**, **Textarea**, **Table**/list, **Button** | Run history rows with status icons. "Test run". Schedule shown in words. |
| Right details pane | **Tabs** (Details / Library / Computer / Routines) + **ScrollArea** | Inline-editable name (hover/click to edit). |
| Library | **ToggleGroup** filter chips + list + **HoverCard** preview | Grouping into Today / This week / Older. Pin. |
| Page view | Full-window route + docked mini chat (assistant-ui Thread, compact) | Share **Dialog** with visibility **Select**. |
| Reactions | **Popover** emoji picker (e.g. `frimousse`) | Badge on the bubble corner, pop animation. |
| Toasts / banners | **Sonner**, **Alert** | Usage-limit banner, reconnect toasts. |
| Settings | **Dialog** or route with sidebar nav + **Card** sections, **Switch**, **Select** | Permissions rule editor ("When it wants to… / It should…"), Vault tabs. |
| Marketplace | Card grid + **Input** search + **ToggleGroup** category pills | Bot detail page with an "Import bot" CTA. |
| Usage | **Progress** meter + shadcn **Chart** (Recharts) | Per-bot breakdown table. |
| Mobile (Expo) | react-native-reusables equivalents of the above | Stack navigation: list → chat → profile sheet. |

---

## 5. Main screens BotDesk needs

1. **Onboarding:** sign-in, "what will you work on", create your primary bot, connect first apps.
2. **Home / bot list (sidebar)**, with sections, pinned, hidden, unread filter.
3. **Bot DM conversation**, with cards (approval, question, computer, work log, draft, routine, page, file).
4. **Group chat / channel**, with roster pane and @mentions.
5. **Bot details pane:** profile, settings (name/title/instructions/notifications/avatar), Library, Routines, Computer.
6. **Computer live view** (full screen, Watching/Take control) plus the Teach-a-task recording bar.
7. **Routine detail / editor** (schedule, triggers, run history, test run).
8. **Page viewer** with docked chat and a share dialog.
9. **Connect apps / plugins**, including custom MCP connector and templates gallery.
10. **Settings:** General (permissions/auto-review rules), Models/Providers (BotDesk-specific), Memory, Vault/secrets, Appearance, Notifications, Usage & billing.
11. **Activity / approvals hub.** Grok Bot doesn't have one; we should add it (see §6).
12. **Marketplace** (browse, bot detail, import) and **command palette**.
13. **Mobile:** bot list, chat, profile sheet, approvals.

---

## 6. "Do better than Grok Bot": UX gaps BotDesk can fill

1. **No approvals inbox.** Pending approvals are scattered across bot chats and expire after 30 minutes. BotDesk should add a global **Inbox / "Needs you"** view (approvals, questions, hand-backs, failed routines) with counts in the sidebar and bulk actions.
2. **Trust settings are only a prompt.** Rules are written in natural language and enforced by a reviewer model (reviewers call this "advisory"). BotDesk should pair natural-language rules with **hard, structured guardrails** (per-app scopes, spend limits, never-send lists) and a visible audit trail per bot.
3. **Shared computer means shared blast radius.** In Grok Bot, logging in with one bot gives every bot that site. BotDesk should support **per-bot credential scopes** and show which bots can reach which accounts.
4. **The status of many bots is hard to see at a glance.** Previews only show the last message. BotDesk should add a **team dashboard / roster view** showing state (working, waiting on you, asleep, failed), current task, and next routine run.
5. **Approval cards are hidden in group chats.** BotDesk should route a group-chat approval to the inbox and show a placeholder in the group instead of dropping it.
6. **Discoverability.** Features are learned from the changelog and docs (e.g. "Teach a task" shows up only in some states). BotDesk should add contextual empty states and a "what can this bot do" card in each bot's first chat.
7. **Light-only marketing, weaker dark mode** (several dark-mode fixes in the changelog). BotDesk should design both themes from the start with tokens (below).
8. **Lock-in.** Grok Bot runs one vendor's models and requires a paid plan. BotDesk should support per-bot model choice (any provider) and self-hosting. This is our core differentiator, so we should show it in bot settings.

---

## 7. Recommended BotDesk palette (original, Grok-adjacent feel)

| Token | Light | Dark |
|---|---|---|
| `--bg` | `#FBFAF8` | `#121211` |
| `--sidebar` | `#F4F3F0` | `#181816` |
| `--surface` (cards, bot bubble) | `#F1F0EC` | `#22211F` |
| `--elevated` (menus, dialogs) | `#FFFFFF` | `#2A2927` |
| `--border` | `#E4E2DD` | `#353431` |
| `--text` / `--text-2` / `--text-3` | `#161615` / `#5F5E5A` / `#8E8C86` | `#ECEAE6` / `#A9A7A1` / `#76746F` |
| `--user-bubble` / text | `#161615` / `#FFFFFF` | `#ECEAE6` / `#161615` |
| `--accent` (BotDesk brand; deliberately not Grok blue) | `#5B5BD6` (indigo-violet) | `#8B8DF8` |
| `--working` | `#D98A00` | `#F5A524` |
| `--success` | `#1A9E5C` | `#2FCB7A` |
| `--danger` | `#D93848` | `#FF5A67` |
| radius | rows/inputs 10 · bubbles/cards 16 · dialogs 20 · pills full | |
| font | Inter / Geist Sans; Geist Mono / JetBrains Mono for code | |

---

## Appendix A — grok.com chat (visual notes; logged-out session)

We captured these logged out. The signed-in sidebar, history and settings were not reachable, and chatting needs sign-up (`07-*`).

- **Layout:** top bar with logo (left), gear menu, Sign in / Sign up (right). Centred H1 "What should we explore?". Composer ~750px wide, radius ~24, with "+" attach, model pill **Fast ▾** (menu: Fast / Auto / Expert / Heavy + a Premium upsell card) and a round blue send button. The composer sits mid-screen when empty and docks to the bottom in a chat. A user bubble appears top right (radius ~16, `#232220` in dark).
- **Tokens (from CSS variables):** `--grok-page-max-width: 800px`; `--grok-radius-control: 10px`; `--grok-radius-island: 22px`; `--grok-radius-overlay: 20px`; `--grok-composer-max-input-height: 176px`; `--header-height: 56px`; durations .12s / .26s / .32s; ease-out-quint. Fonts: "X-VF"/universalSans body (15px), "X Mono" code.
- **Colours:** light bg `#F9F8F7`, pane `#FEFEFC`, text `#2C2C2B` (secondary 62%, tertiary 44%), borders `#D4D3CF`/`#E6E5E3`, accent `#1084FE`. Dark bg `#131211`, chat `#1E1D1D`, pane `#282726`, popover `#23211F`, text `#E6E5E3` (65%/47%), borders `#5F5E59`/`#383836`, success `#00C972`, danger `#FF263C`.
- **Settings (logged out):** popover with a 3-segment theme switch (Light / Dark / System icons), Language, Feedback.
- **Composer details:** placeholder rotates ("Type / to use slash commands", "Type @ to search your apps", "Switch to Build Mode to create apps"). Slash commands and @apps are supported.
- **Mobile (390px, viewed but not saved):** the header keeps the logo and Sign in/up, the H1 sits centred, the composer docks to the bottom, and the cookie sheet is full width.

## Appendix B — screenshots (`docs/research/grok-screens/`)

| File | Shows |
|---|---|
| `01-landing-logged-out-empty.png` / `02-…-dark.png` | grok.com empty state, light/dark |
| `03-login-modal-on-attach-dark.png` | Attach → login modal |
| `04-model-picker-dark.png` | Fast/Auto/Expert/Heavy menu |
| `05-settings-menu-logged-out-dark.png` | Theme switch popover |
| `06-composer-typed-dark.png` · `07-first-message-signup-wall-dark.png` | Composer with text; sign-up wall after send |
| `10-xai-bot-overview-part1..3.jpg`, `…part4-pricing.jpg`, `…-full.jpg` | x.ai/bot landing (hero mock, feature cards, Teach-a-task bar, memory line, pricing) |
| `11-xai-bot-marketplace.jpg` · `14-xai-bot-marketplace-bot-detail(-b).jpg` | Marketplace grid and bot detail |
| `13-hero-app-mock-a.jpg`, `-b-top.jpg`, `-c-computer-card.jpg` | **Best in-app reference:** sidebar, DM transcript, computer card, work log, routine line |
| `15-guide101-cloud-computer.jpg` | Bot's remote desktop |
| `15-guide101-anatomy-of-a-bot.jpg` | 3-pane app with right "screen + Routines" pane |
| `15-guide101-bot-settings.jpg` | Settings pane (Name/Title/Description/Notifications), Running task card |
| `15-guide101-routines-triggers.jpg` | Routine detail pane (Active, Test run, When to run, Run history) |
| `15-guide101-account-menu-and-right-pane.jpg` | Account menu (iOS, Settings, About, Help, Feedback, Log out) |
| `15-guide101-multi-bot-chain.jpg` | Question card with options; sidebar sections incl. Unassigned/Hidden Bots |
| `16-teams-guide-new-channel-menu-and-roster.jpg` | "+" → New Bot / New Channel; channel Members roster |

Sources: x.ai/bot · x.ai/news/introducing-grok-bot · x.ai/bot/marketplace · x.ai/bot/guides (grok-bot-101, how-i-run-multiple-teams-of-grok-bots, designing-grok-bot-with-grok-bot) · x.ai/changelog/bot · docs.x.ai/grok-bot/{overview, chat-and-collaboration, bots, approvals-security-and-privacy, computer-and-apps, skills-routines-and-automations, files-and-results} · reviews: eesel.ai/blog/grok-bot-review, composio.dev/blog/guide-to-frok-bot.
