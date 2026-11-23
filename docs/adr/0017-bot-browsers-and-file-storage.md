# 0017: Bot browsers and file storage, bring your own provider

- Status: accepted (owner, 2026-11-23: the recommended answers below, plus the folder layout in §3)
- Date: 2026-11-23
- Based on: [ADR 0004](0004-agent-runtime-and-safety.md) (policy, taint), [ADR 0008](0008-free-and-open-source.md) (free, bring your own keys), [ADR 0010](0010-connections-and-credentials.md) (vault, bot-owned accounts), [high-level.md §6](../architecture/high-level.md#6-bot-computers-sandboxes) (full computers)
- Changes: the build order for "Bot computers" in [ROADMAP](../ROADMAP.md): a browser and files come first, the full computer later

## Context

high-level.md §6 plans a **computer** per bot: a Linux desktop in a container or microVM, with a live screen and take over. That means running containers (Docker + gVisor, or E2B), which the owner can't operate, and which a slow 8 GB machine can't test.

Most of what people want a computer for is **the web** (sites with no API or plugin) and **keeping files** (downloads, screenshots, reports). Both can be had without running a sandbox:

- **Browsers** are sold as a service, and they all speak the Chrome DevTools Protocol (CDP), so Playwright drives any of them through `connect_over_cdp`. A browser can also run on the BotDesk server itself (Playwright's own Chromium).
- **Storage** is a commodity. Most cloud storage speaks the S3 API, so one adapter covers many services. A folder on the server's disk works too.

BotDesk is free and people bring their own keys (ADR 0008). So the same rule applies here: the organization picks a provider and pastes its key, and a **Local** option works with no account at all.

Prices and free plans checked on 2026-11-23. They change often; the Settings screen links to each provider's pricing page instead of quoting numbers.

| Browser provider | Free | Paid | Notes |
|---|---|---|---|
| **Local** (Chromium on the BotDesk server) | Free | — | Uses the server's RAM (~300–500 MB per open browser). Playwright downloads Chromium once (~150 MB) |
| **Steel** (cloud) | Monthly or starter credits | ~$0.10 per browser hour | Browser is open source (Apache-2.0), so **Steel self-hosted** is the same adapter with your own address |
| **Browserbase** | 1 browser hour a month | from $20 a month | Best known. "Contexts" keep logins between sessions; live view URL |
| **Kernel** | Monthly credits | ~$0.06 per browser hour | Live view, saved profiles |
| Later: Hyperbrowser, Anchor, Browser Use Cloud, Cloudflare Browser Run | | | Same CDP adapter shape. Browserless's self-host image is SSPL (needs an ADR); its cloud would be fine |

| Storage provider | Free | Notes |
|---|---|---|
| **Local folder** (on the BotDesk server) | Free | Lost on hosts with throwaway disks; the Settings screen says so |
| **S3-compatible**: AWS S3, **Cloudflare R2** (10 GB free, no download fees), Backblaze B2 (10 GB free), Tigris (5 GB free), Wasabi, DigitalOcean Spaces, Supabase Storage, Google Cloud Storage (HMAC keys), MinIO or Garage self-hosted | Depends on the service | **One adapter** for all of them: endpoint, region, bucket, access key, secret, optional folder prefix |
| **Cloudinary** | 25 credits a month (storage + bandwidth + transformations) | Best for images and screenshots (previews, resizing). Non-image files max 10 MB on the free plan |
| Later: Azure Blob | | Its own API |

Google Drive, Dropbox and OneDrive are **members' apps**, not where bots keep their working files: they come as plugins with connections (ADR 0010), like Gmail.

## Decisions

### 1. Words

- A bot's **Browser**: a web browser the bot drives, run by the organization's **browser provider**. Its **browser profile** (cookies, sign-ins) is kept between sessions, one per bot.
- A bot's **Files**: its own folder in the organization's **file storage**, kept by a **storage provider**.
- A **Computer** stays what GLOSSARY.md says: a full desktop sandbox. It is built later (high-level.md §6 unchanged).
- A bot's computer setting becomes: **None**, **Browser and files**, **Full computer** (coming soon). It replaces `computerMode` (`own | shared | none`).
- GLOSSARY.md gets Browser, Browser profile, Files, Browser provider and Storage provider when this ADR is accepted.

### 2. One browser provider and one storage provider per organization

- Owners and admins choose both in **Settings → Computers**: a card each, a provider list, the provider's fields, and **Test** (start and stop a browser; write, read and delete a small file).
- Keys are sealed by the vault like model keys (Fernet from `SECRET_KEY`), shown as the last 4 characters only.
- With nothing chosen, both are **Local**, so a fresh install works with no account. The server's operator can turn Local off (`LOCAL_BROWSER=false`, `LOCAL_FILES=false`), for example on a host with little RAM or a throwaway disk.
- Per-bot providers are left for later. One choice per organization keeps Settings simple, and every bot's files stay in one place.

### 3. Two small interfaces, one adapter per provider

- `BrowserProvider`: `start(profile_id) → BrowserSession(cdp_url, live_view_url | None)`, `stop(session)`, `test()`. The bot's tools drive the session with Playwright over CDP, so tools are written once for every provider.
  - Local: Playwright `launch_persistent_context` with one profile folder per bot under `DATA_DIR`.
  - Cloud: the provider's REST call to create a session with the bot's saved context or profile, then its CDP URL.
- `FileStorage`: `put`, `get`, `delete`, `list`, `signed_url(expires)`, `test()`.
  - Local, S3-compatible (and later Azure) through one object-store library. Candidates: `obstore` (one async API for local, S3, GCS and Azure) or `aioboto3`. Check licence and API with Context7 before coding.
  - Cloudinary through its REST upload and admin API over `httpx` (no SDK needed).
- A `files` table in Postgres is the list of record: org, bot (none for shared), path, size, type, sha256, storage key, provider, the run that made it, created at. The UI lists files from it, never by listing a bucket.
- **Folders (owner, 2026-11-23):** everything goes under a `botdesk/` folder, with one folder per bot named after its @handle and `botdesk/shared/` for files every bot in the organization may read: `botdesk/inbox-manager/reports/march.csv`. In the organization's own bucket that is `{prefix}/botdesk/…`; Local keeps each organization apart, `{FILES_DIR}/{org id}/botdesk/…`. Connecting storage creates `botdesk/`, a short README, and a folder for each bot. A file keeps its key if the bot's handle changes later; new files go to the new folder.
- Changing provider doesn't move old files. They stay readable while the old provider's settings are kept; a "copy files over" job can come later.

### 4. What a bot can do, through the normal policy

Two core plugins (always loaded, like Team), `files` and `browser`. A bot gets them through a binding (ADR 0010): new bots have them on, existing bots get a binding when each lands, and the bot's Tools tab can switch them off.

| Tool | Risk class |
|---|---|
| `browser.open`, `browser.read_page` (text and an accessibility snapshot with element refs), `browser.screenshot`, `browser.back` | `read` |
| `browser.click` on a link, or a form that only searches (GET); `browser.type` into a search box | `read` |
| `browser.click` on a button or a form that posts; `browser.type` into any other field; `browser.select` | `write-external` |
| `browser.upload` (a file to a page) | `external-send` |
| Typing into a password field | refused: the bot asks for **take over** (§5) |
| `files.list`, `files.read` | `read` |
| `files.save` (also where downloads and screenshots go) | `write-internal` |
| `files.share_link` (a link anyone with it can open) | `credential` |
| `files.delete` | `destructive` |

- The risk of a click is read from the element it targets (tag, type, its form's method), just before the click.
- **Taint (ADR 0004 §5) applies as is.** A web page is outside text, so after the first `read_page` every `write-external` call in that run asks a person. This is the safe default, and it means a bot filling a long form asks often. See owner decision 4.
- One browser per bot at a time. A session closes after 10 minutes without a tool call, and at the end of the run. Pages are capped (text and screenshot size) before they reach the model.
- Downloads go to the bot's Files and are never opened or run.

### 5. Sign-ins: take over, never a password

- The bot never gets or types a password. When a page needs a sign-in (a password field, or the bot says so), the run asks for **take over**: an approval card "Sign in to example.com for Inbox Manager".
- The member opens the **live view** in the bot's Computer tab, signs in (2FA and CAPTCHAs included), and presses Done. The run carries on, and the sign-in stays in the bot's browser profile.
  - Cloud providers: their live view URL in a frame (Browserbase, Steel and Kernel all have one).
  - Local: BotDesk's own view, CDP screencast frames out and mouse and keyboard in, over the API's WebSocket with the member's session.
- A browser profile is **bot-owned**, like a bot's own mailbox (ADR 0010 §3): every member who can talk to the bot uses what it is signed into. The take-over card and the Computer tab say so in one line.
- "Forget sign-ins" in the Computer tab clears the profile.

### 6. Safety

- The **Local** browser refuses private and internal addresses (the same rules as `core/url_guard.py`, checked on every request the page makes) unless `ALLOW_PRIVATE_BROWSER_URLS=true`. Without that, a bot could read the server's own network. Cloud browsers run on the provider's network, so this is theirs.
- An S3 endpoint someone types goes through the same guard (MinIO on your own network needs `ALLOW_PRIVATE_STORAGE_URLS=true`).
- Files: 25 MB per file. Local storage has a per-organization quota (default 5 GB).
- Screenshots the bot takes for itself (not ones it saves) are kept 7 days, then deleted.
- Browser time is billed by the provider, not BotDesk. Usage shows browser minutes per bot, and the bot's budget can't see provider bills, so the Settings card says so.

### 7. Build order

1. **Files**: `FileStorage` with Local and S3-compatible, the `files` table, Settings → Computers (storage card), `files.*` tools, a Files list in the bot's Computer tab, and files attached in chat.
2. **Local browser**: `BrowserProvider` with Local, the `browser.*` tools and their risk classes, screenshots into Files, the private-address guard.
3. **Take over**: the take-over approval, live view for Local, saved profiles, "Forget sign-ins".
4. **Cloud browsers**: Steel (cloud and self-hosted), Browserbase, Kernel, each with its live view.
5. **Cloudinary** storage.
6. Later: the full computer (high-level.md §6), more providers, routine recording.

Each step is usable on its own and ends with tests and a browser check.

## Trade-offs

- A browser is not a desktop: no desktop apps, no terminal, no CLIs. The full computer still covers those, later.
- A Local browser costs the server RAM and makes it reach the open web; a weak server will want a cloud provider.
- Reading the risk from the clicked element is a guess. A plain button can still send or buy something, which is why buttons and posting forms are `write-external` and ask.
- Bring-your-own means each organization signs up somewhere for anything beyond Local. In exchange BotDesk never pays for or holds anyone's browsing or files.

## Owner decisions (answered 2026-11-23: all as recommended)

1. **With nothing set up, use Local for both** (recommended), or ask the admin to choose first?
2. **One provider per organization** (recommended), or a choice per bot now?
3. **First cloud browsers: Steel, Browserbase, Kernel** (recommended), or others?
4. **Many approvals while a bot browses** after reading a page. Keep ADR 0004 as is (recommended for v1), or add "Allow on this site for this run" to the approval card: a person lets the run click and type on one site until it ends (never `spend`, `destructive` or `credential`)? The second changes ADR 0004 §5.
5. **Keep the bot's own screenshots 7 days** (recommended)?
6. **Build order** as §7, files first (recommended)?

## Update 2026-11-23: steps 1 and 2 as built

- **Files** (step 1) shipped without "files attached in chat"; that comes with the chat composer work. The shared folder is `botdesk/_shared` (handles only hold a-z, 0-9 and "-", so it can't clash with a bot's folder). Storage settings live in `computer_providers` (one row per organization and kind; none means Local).
- **Local browser** (step 2): instead of one `browser.click` whose risk depends on the element, each risk has its own tool, so the policy decides before anything runs: `follow` (links) and `search` (search boxes) are `read` and refuse anything else; `click`, `type` and `choose` are `write-external` and name the element in words (`what`, `field`) that must match its label, which is what the approval card shows. `BrowserProvider` as an interface arrives with the first cloud provider (step 4); today there is `LocalBrowsers`.
- The Docker image has no browser yet; that and cloud providers are the next decision.

## Update 2026-11-23: after the review

- S3-compatible storage no longer uses obstore: it followed redirects, so a public endpoint could send BotDesk's requests to the server's own network. `src/storage/s3.py` now signs with SigV4 (checked against AWS's published example) and uses the guarded HTTP client (pinned public addresses, no redirects), which also closes DNS rebinding for storage.
- A bot's folder is `botdesk/<handle>/` unless another file already holds the key (a reused handle): then `botdesk/<handle>-<id8>/`. Removing a bot deletes its files from storage.
- The approval words for `click`, `type` and `choose` must contain the element's whole label; unlabelled elements are refused. `search` requires that Enter sends with GET, including the default button's `formmethod`.
- Step 4 (cloud browsers) built: Steel, Browserbase and Kernel behind `src/browser/cloud.py`, chosen in `PUT /orgs/{id}/browser-provider` (a `computer_providers` row of kind "browser"), a profile per bot in `browser_profiles`. Only opening a page starts a browser; every other tool works on the one that's open. The Docker image still has no Local browser: use a cloud provider there.
- Step 5 (Cloudinary) built in `src/storage/cloudinary.py`: private uploads read back through the signed download call, signatures checked against Cloudinary's documented examples.
- Still open: the Local browser's address check resolves names once, so DNS rebinding can get past it (Chromium resolves again); the local quota check isn't atomic under concurrent saves.
