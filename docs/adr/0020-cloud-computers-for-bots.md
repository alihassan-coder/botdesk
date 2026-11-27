# 0020: Cloud computers for bots (Orgo first)

- Status: accepted (owner asked for it on 2026-11-27: "give the computer to my AI agent", each bot picks what it needs, show the screen)
- Date: 2026-11-27
- Based on: [ADR 0004](0004-agent-runtime-and-safety.md) (risk, approvals, taint), [ADR 0008](0008-bring-your-own-keys.md) (bring your own keys), [ADR 0017](0017-bot-browsers-and-file-storage.md) (Files and browsers, take over)
- Research: [docs/research/orgo-api.md](../research/orgo-api.md) (from Orgo's OpenAPI, fetched 2026-11-27)

## Context

A bot can read files and drive a browser (ADR 0017), but it can't run anything: no shell, no tests, no build. Asked to fix a bug from Jira and test it, it can only edit blind through GitHub. The owner wants bots to have a real computer, shown live, with each bot choosing what it needs.

[Orgo](https://www.orgo.ai) rents cloud computers (Linux by default) with a REST API: create, start, stop, delete, screenshot, click, type, run shell commands (`POST /computers/{id}/bash`, up to 300 s), long-running apps (`services`, with logs), and public URLs for a port. A user creates a key at orgo.ai/api-keys (`Authorization: Bearer sk_live_…`). A medium computer costs about $0.055 an hour while running and almost nothing stopped; the free tier has starting credit. Orgo can also run its own agent loop, which BotDesk won't use: its clicks would skip BotDesk's approvals.

## Decisions

### 1. A computer provider per organization, with the organization's own key

Settings → Computers gets a third card, **Cloud computer**, next to Storage and Browser. An owner or admin picks **Orgo** and pastes a key. BotDesk checks it live (`GET /api/me`), finds or creates a workspace named "BotDesk" for the bots' computers, and keeps the key sealed by the credential vault (shown as its last 4). Removing the key first stops the bots' computers (best effort), then forgets it. Other providers can be added behind the same interface later (`ComputerProvider`, like the browser providers).

### 2. Each bot picks Browser or Computer

A bot has `computer`: **browser** (the default: today's Files and browser) or **cloud** (its own cloud computer). Only owners, admins and whoever may edit the bot change it, and **cloud** needs the organization's provider. A cloud bot keeps **Files** (chat attachments and the shared folder live there) and loses the browser tools (its computer has its own browser). Switching back to browser stops the computer; deleting it is a separate, confirmed action (its disk holds the bot's work).

### 3. One computer per bot, started on demand, stopped when idle

- Made on first use (a tool call, or Start in the bot's Computer tab): Linux, 2 vCPU, 8 GB, named `botdesk-<handle>`. One at a time per bot: a row lock decides who creates it.
- Started when a stopped one is needed; **stopped after `COMPUTER_IDLE_MINUTES` (default 20)** without a tool call, a take-over input or someone watching. A job checks every minute. A free Orgo account can't set Orgo's own auto-stop, so BotDesk does it for everyone.
- Deleted when its bot is removed (best effort, after the commit). Its disk survives stop and start.
- Computer time is recorded as usage (`kind: "computer"`) at the provider's list price (`ORGO_PRICE_PER_HOUR`, default $0.055), so the organization's budget and usage page see it.

### 4. Tools (core plugin `computer`, offered to cloud bots only)

| Tool | Does | Risk | Notes |
|---|---|---|---|
| `computer.inspect` | A **read-only** command (`ls`, `cat`, `grep`, `git status`…) | read | A strict parser allows only listed programs and flags, pipes between them, no redirection, no `$(…)`, no `;`. Never asks. |
| `computer.run` | **Any** shell command, in an optional folder, up to 300 s | write-external (open egress) | Asks under *Ask before acting*; the approval card shows the exact command, editable before approving. Output: exit code, time, and the first and last 8 KB. |
| `computer.start_app` | A long-running process (dev server, worker) as an Orgo service with a port | write-external | Restarts on failure; `computer.app_logs` (read) reads its log; `computer.stop_app` (write-internal) stops it. |
| `computer.preview` | Makes a URL for a port | external-send | Private to the Orgo workspace's members unless the Orgo plan allows a link; the chat shows it either way. |
| `computer.open` | Opens an address in the computer's browser | read, open egress | So people watching the live screen see the app. Its page isn't read back. |
| `computer.screenshot` | Saves the screen to the bot's Files | read | People see it as a file; the model reads it once bots see images ([ADR 0018](0018-bots-see-images.md)). |
| `computer.upload` / `computer.download` | Copy a file between Files and the computer (10 MB) | write-internal | Through the shell, base64 in chunks. |

Every computer tool's output is **outside text** (`untrusted_output`): a run that read it is tainted, so from then on anything above write-internal asks (ADR 0004 §5). `computer.run` is not idempotent: a call cut off mid-way stops the run for a person.

**Clicking and typing for the model** wait for ADR 0018 (the model must see the screen). People can click and type now (§5).

### 5. Watch and take over

The bot's Computer tab shows the screen live: the web asks the API for a JPEG about once a second (`GET …/computer/screen`, Orgo's screenshot, scaled), only while the tab is visible. Taking over sends clicks and text through the API (`POST …/computer/input`: Orgo's click and type; keys and scrolling through `xdotool` on the computer). **The VNC password (root on the machine) never leaves the API**, and no Orgo key reaches a browser. People who also have the Orgo account get an "Open in Orgo" link.

### 6. Failures say what to do

No provider: "An owner or admin can add an Orgo key in Settings → Computers." Key refused (401): the provider shows "key refused" and tools say so. Out of credit (402): "Orgo says the account is out of credit." No room in the region (503): try again later. Computer gone at Orgo (404): forgotten; the next use makes a new one and the bot is told its old files are gone.

### 7. How bots work on a computer (prompt)

A cloud bot's instructions get a short working method, from how strong coding agents work: look before changing (inspect), make small steps, run the tests and read exit codes, use non-interactive flags, put long jobs in an app or the background with a log, never print secrets, and report with evidence (the command and its result). Before pushing, deploying or anything leaving the computer it says what and why: that's what the approval card shows.

## Trade-offs

- Commands are judged by tool, not by parsing every shell command: `inspect` is narrow on purpose, and everything else asks (unless the bot is autonomous and the run untainted). Safer than guessing what an arbitrary command does; a little more asking.
- The live view is screenshots, not video: no VNC library (noVNC is MPL-2.0) and no root password in browsers, at about one frame a second.
- Orgo is a young company: one provider interface, so another can be added.
- Model clicking waits for ADR 0018.
