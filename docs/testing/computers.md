# Cloud computers, by hand (Orgo)

Check bots' cloud computers ([ADR 0020](../adr/0020-cloud-computers-for-bots.md)) against a real Orgo account. Allow about 30 minutes. A medium computer costs about $0.055 an hour while it runs; a free Orgo account's starting credit covers this guide many times over.

The steps use the API's docs page (<http://localhost:8000/api/docs>, signed in as the owner in the same browser) or the web app where it already has the screen. `{org}` is your organization's id and `{bot}` the bot's.

## Before you start

- [ ] `pnpm dev` runs both apps; you're signed in as an owner.
- [ ] An Orgo account: sign in at [orgo.ai](https://www.orgo.ai), open **API keys** (orgo.ai/api-keys) and create a key. It starts with `sk_live_`. Keep the tab open.
- [ ] A bot with a working model key (Settings → Models & keys), set to **Ask before acting**.

## 1. Add the key

- [ ] `PUT /api/v1/orgs/{org}/computer-provider` with `{"provider": "orgo", "apiKey": "sk_live_…"}`. The answer has `provider: "orgo"`, your key's last 4 and `status: "ok"`.
- [ ] At orgo.ai there's now a workspace called **BotDesk** (it's made once; saving the key again finds it).
- [ ] A wrong key (change one letter): 400 "That key didn't work: Orgo refused it…". The answer never shows the key.
- [ ] As a member (second browser): the same PUT is 403; `GET …/computer-provider` works.

## 2. Set a bot to Cloud

- [ ] `PATCH /api/v1/orgs/{org}/bots/{bot}` with `{"computer": "cloud"}`. The bot comes back with `computer: "cloud"`.
- [ ] Its Tools now offer the Computer tools and no Browser tools (ask it "what tools do you have?").

## 3. Ask it to run `uname -a`

- [ ] In the bot's DM: "Run `uname -a` on your computer and tell me the result."
- [ ] The first time, the computer is made: at orgo.ai a computer named `botdesk-<handle>` appears in the BotDesk workspace (Linux, 2 vCPU, 8 GB). It can take a minute.
- [ ] An approval card appears for **Run a command**: it shows the whole command in an editable box. Edit it to `uname -a && whoami`, then approve.
- [ ] The bot answers with the result: the kernel line and `root`, and the exit code 0.
- [ ] Ask "list the files in your home folder": it uses `computer.inspect` (`ls -la ~`) and **doesn't** ask.
- [ ] Ask for something that writes (`touch ~/hello.txt`): it asks first (only `computer.run` can do that).

## 4. Watch the screen

- [ ] `GET /api/v1/orgs/{org}/bots/{bot}/computer`: `status: "running"`, `idleStopsAt` about 20 minutes away, `orgoUrl` opens the computer at orgo.ai. The answer has no password and no IP address.
- [ ] `GET …/computer/screen` shows the desktop as a JPEG (the web's Computer tab shows it live).
- [ ] Ask the bot to open `https://example.com` on its screen (`computer.open`): the next screenshot shows it.

## 5. Take over

- [ ] `POST …/computer/input` with `{"kind": "click", "x": 640, "y": 360}`, then `{"kind": "type", "text": "hello"}`, then `{"kind": "key", "key": "Enter"}`: each answers 204 and the screen changes.
- [ ] `{"kind": "scroll", "direction": "down"}` scrolls the page.
- [ ] `{"kind": "key", "key": "alt+F4"}` is refused (422): only the listed keys.

## 6. Preview an app

- [ ] Ask: "Start a web server on port 8000 that serves your home folder, and give me a preview link." It should use `computer.start_app` (asks first) with something like `python3 -m http.server 8000 --bind 0.0.0.0`, then `computer.preview` (asks first: a link leaves the computer).
- [ ] The link is `https://…web.orgo.dev`. Opening it asks you to sign in to Orgo (new links are private to the workspace); signed in, you see the folder listing.
- [ ] `GET …/computer` lists the app under `apps` and the link under `previews`.
- [ ] Ask it to read the app's log (`computer.app_logs`), then stop the app (`computer.stop_app`).

## 7. Files both ways

- [ ] Attach a small text file in the chat and ask the bot to copy it to its computer and `cat` it (`computer.upload` asks first and shows where it goes, then `computer.inspect`).
- [ ] Ask it to copy a file to `~/.bashrc` or into a `.git` folder: it's refused (no hidden files or folders), before anyone is asked.
- [ ] Ask it to save a screenshot (`computer.screenshot`): a PNG appears in its Files under `screenshots/`.
- [ ] Ask it to copy `/etc/os-release` from the computer to its Files (`computer.download`): it appears under `downloads/`.

## 8. Idle stop and usage

- [ ] Leave the computer alone (no chat, no Computer tab open) for `COMPUTER_IDLE_MINUTES` (20; set it to 10, the least, in `apps/api/.env` and restart to wait less). Within a minute after that, `GET …/computer` says `stopped`, and orgo.ai shows the computer stopped.
- [ ] Settings → Usage (or `GET /api/v1/orgs/{org}/usage`) shows the computer's time for the bot, at $0.055 an hour.
- [ ] Ask the bot to run something again: the computer starts by itself (it can take a minute), with your files still there (`ls ~`).
- [ ] `POST …/computer/stop` stops it at once; `POST …/computer/start` starts it again.

## 9. Failures and clean-up

- [ ] Delete the computer in Orgo's dashboard, then ask the bot to run `ls`: it makes a new one and says the old files are gone.
- [ ] Revoke the key at orgo.ai, then ask the bot to run `ls`: it says Orgo refused the key, and `GET …/computer-provider` shows `status: "key_refused"`. Add a new key to fix it.
- [ ] Set the bot back to Browser (`{"computer": "browser"}`): its computer stops; its Browser tools are back.
- [ ] `DELETE …/computer` deletes the computer at Orgo (everything on it).
- [ ] Delete a bot whose computer runs: the computer disappears at orgo.ai within a minute or two (BotDesk tries again until Orgo confirms).
- [ ] `DELETE …/computer-provider` (owner): the bots' computers stop first, then the key is forgotten (409, and the key stays, if one can't be stopped). Delete the leftover computers and the BotDesk workspace at orgo.ai if you're done.
