# Test everything by hand

One checklist for the whole app, so you can check every feature yourself before a release. Tick each box as you go. The automated tests (`pnpm check`) already cover the logic. This list checks what only a person can see: does it look right, does it feel right, and does it work against the real API.

Allow about 2 hours for everything, plus about 30 minutes for the Google setup (once). The two longest parts have their own guides:

- [Gmail](gmail.md): read, organise, draft and send email, and react to new email
- [MCP servers](mcp.md): add a server, review its tools, sign in

## Before you start

- [ ] `apps/api/.env` has `DATABASE_URL` and `SECRET_KEY` (keys are encrypted with it), plus `PLUGINS=demo,gmail` if you'll test Gmail.
- [ ] `apps/web/.env.local` has `NEXT_PUBLIC_API_URL=http://localhost:8000`.
- [ ] `pnpm dev` starts both apps (the API runs its migrations on start). Web: <http://localhost:3000>, API: <http://localhost:8000/docs>.
- [ ] Use two browsers (or a normal and a private window), so you can be two people at once: **Owner** and **Member**.
- [ ] Check each screen once on a phone-sized window too (browser dev tools → 375 px wide) and once in dark mode (Settings → Appearance).

## 1. Accounts

- [ ] Sign up as Owner. You land in your new organization.
- [ ] Sign out, sign in again. A wrong password shows the API's message.
- [ ] Forgot password: the reset email (or the API console, without Brevo) has a link; it works once and the old password stops working.
- [ ] Settings → Profile: change your name and @handle; change your password (your other browser is signed out).
- [ ] "Explore the demo" on /sign-in opens demo data with a banner; "Create an account" leaves it. Nothing from the demo appears in your real org.

## 2. First-time setup (`/welcome`)

- [ ] A brand-new owner with no bots goes to `/welcome`: name the org, add an AI key (or Skip), hire Chief, connect Gmail (or Skip).
- [ ] Finish opens Chief's DM, which starts with Chief introducing itself.
- [ ] Reloading `/` doesn't send you back to setup. Invited members never see it.

## 3. Organization and members

- [ ] Settings → Organization: rename it; the sidebar switcher follows.
- [ ] Org switcher → Create organization: you're its owner and land in it; switching back and forth reloads the right bots and chats.
- [ ] Settings → Members: invite Member by email; the dialog also shows a link. Open it in the second browser, sign up, and you join the org.
- [ ] Change Member's role to admin and back; only an owner sees "Owner" in the role picker; you can't remove the last owner.
- [ ] Revoke a pending invite: its link stops working.

## 4. Models and keys

- [ ] Settings → Models & keys: add a key for one provider. "Checking…" then connected with `••••1234`. A wrong key shows the provider's reason.
- [ ] Test, Replace and Remove work. The model list shows prices and context windows; Refresh reloads it.
- [ ] My keys: as Member, add your own key. Owner can't read it; Member's runs use it as the settings page says, and nobody else's do.
- [ ] Create a bot and pick a model with the searchable picker.

## 5. Bots and chats

- [ ] Create a bot from scratch (`/bots/new`) and from the Marketplace (Hire). Hiring Chief gives it chief-of-staff instructions.
- [ ] Message a bot in its DM: typing dots, words stream in, the reply is saved (reload shows it). Stop ends a reply mid-way.
- [ ] Without any AI key, the bot answers with the stand-in reply (no crash).
- [ ] New group with two bots and Member: the lead answers messages with no @mention; @mention another bot and it answers; bots handing over to each other stop after 3 hops with a notice.
- [ ] In a DM, @mention another bot: it joins as a guest and replies with its own name.
- [ ] Group details pane: rename the group, add people or bots, remove one. Member (second browser) sees the change live; a removed person loses the group.
- [ ] As Member, Leave group at the foot of a group's details (Stay keeps you in): the group leaves your list and you land home; Owner sees you gone live. Leaving a group you're alone in says it's deleted, and it is.
- [ ] Unread counts: Member sends a message in a group; Owner's chat list shows a badge within about 20 s, and it clears when Owner opens the chat.
- [ ] Edit a bot (name, instructions, model, memory switch, budget) and remove a bot.

## 6. Approvals and security levels

- [ ] Settings → Security: the default for new bots, and the **ceiling**: a bot can't be set above it, and lowering it makes stronger bots act at the ceiling.
- [ ] Bot on "Ask before acting": ask it to "send an email" (Demo plugin). The approval card shows exactly what will be sent. Approve, Edit (change a field) and Deny each do the right thing, and the bot continues.
- [ ] Two people decide the same approval at once: only one decision wins and the other sees who decided.
- [ ] Approvals page: pending and past decisions, the bot filter, the sidebar count.
- [ ] Bot on "Read only": it can't draft or send, and says so.
- [ ] A bot that read outside text (an email, a web page) always asks before sending, even on Autonomous.

## 7. Handoffs (bots working together)

- [ ] Ask Chief to plan something that needs teammates (e.g. "plan the launch with sales and inbox"). Handoff cards appear: Queued → Working… → Done.
- [ ] Chief shows "waiting for @…", then posts one combined answer. "View reply" jumps to the teammate's reply.
- [ ] Stop while teammates work: open tasks show Cancelled.

## 8. Memory, usage and budgets

- [ ] Tell a bot a fact, then ask about it in a new message: it remembers (only with `MEMORY_ENABLED` and an OpenAI key; otherwise the screen says memory is off).
- [ ] Settings → Memory: search, Correct and Forget a memory; Forget everything (owner/admin only).
- [ ] Settings → Usage & budgets: today's spend appears after replies. Set a tiny bot budget: the next reply stops with a budget notice and a link to raise it.
- [ ] Member can't change budgets (read-only with a note).

## 9. Routines

- [ ] Create a routine (bot, what to do, when, time zone). A "Created a routine" card appears in your DM.
- [ ] Run now: the run replies in your DM. Switch off, edit, delete.
- [ ] Let one run on its schedule (set it a few minutes ahead).

## 10. Connect apps and bot Tools

- [ ] Connect apps lists Built in (Demo), Gmail (Ready or Not set up), and the "Coming soon" catalogue with real logos (light and dark).
- [ ] Connect the Demo with a label and key. Disconnect behind a confirm.
- [ ] Bot details → Tools: switch a plugin on/off and pick an account; only accounts you may use are offered.
- [ ] Gmail: follow [gmail.md](gmail.md) completely.
- [ ] MCP: follow [mcp.md](mcp.md) completely.

## 11. Everywhere

- [ ] ⌘K / Ctrl+K opens the command palette; shortcuts work.
- [ ] The sidebar collapses to an icon rail; the logo expands it.
- [ ] Phone width: bot list first, chats full screen, details pane as a sheet, nothing cut off or scrolling sideways.
- [ ] Dark mode on every screen above: text readable, no white flashes.
- [ ] Keyboard only: you can reach and use every button on the chat, approval card and settings screens; focus is always visible.

## If something's off

Write down the screen, what you did, what you expected and what happened, plus the API console's last lines. That's enough to turn it into a fix.
