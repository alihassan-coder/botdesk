# Competitor research: AI teammates and always-on agents

> Researched 2026-11-11. This market changes weekly. Re-check pricing and availability before quoting them.
> Confidence tags: **[primary]** means an official vendor page was read directly. **[secondary]** means press or blog coverage only. **[single-source]** means only one source was found.

## TL;DR

- **The owner's "GPT dots" is OpenAI's _dots_.** OpenAI launched it on **2026-09-29** ("Introducing dots"). Dots are always-on agents inside ChatGPT. Each one has its own cloud computer, and you reach it through ChatGPT, Slack, Teams and iMessage/RCS.
- **Meta's product is _Muse_.** Meta launched it on **2026-09-08**. Muse is a personal AI agent with its own cloud VM ("Muse Secure VM") and a separate approval agent called Sentinel. It runs on iOS, Android, muse.ai and WhatsApp.
- Other notable products:
  - **Anthropic Claude Tag** (2026-06-23), a shared team agent in Slack.
  - **Anthropic Claude Duet** (2026-10-21), a proactive personal agent.
  - **Google Gemini agent with coworker agents** (2026-10-08/09).
  - **Manus Cue** (2026-09-28).
  - **Microsoft Agent 365** (GA 2026-05-01), the governance layer.
- **Grok Bot is still the only product built around a _team_ of named bots** with group chat, a chief-of-staff bot, learning by watching, and a marketplace. OpenAI and Meta both ship a single personal agent. Each says multi-agent teams are coming.
- **Open source:** OpenClaw (MIT, ~394k stars) and Hermes Agent (MIT, ~263k stars) lead "personal agent" open source. Several direct open-source Grok Bot clones already exist. The strongest are **OpenMausBot** (Apache-2.0, ~21k stars) and **Rakazo** (Apache-2.0, ~7.9k stars). BotDesk is entering a crowded open-source field and needs a sharp angle.

---

## 1. Products

### 1.1 Grok Bot (SpaceXSI, formerly xAI): the reference product

| | |
|---|---|
| **Launch** | 2026-08-11, beta. Enterprise GA with admin, network and audit controls on 2026-09-03 [secondary]. **Team Bots** public beta on 2026-09-28 [primary]. |
| **What it is** | "AI teammates you can give real work to." You message bots like colleagues. They sign into your tools, use them like a person would, and come back with finished work or an approval request. |
| **Core concepts** | Bots, a cloud computer, routines ("follow along"), memory, group threads ("Connect the Bots"), a Chief of Staff bot, Team Bots (shared and role-based), plugins, credentials, skills, the Marketplace, and separately metered usage. |
| **Where it runs** | Desktop on macOS and Windows, with Linux .deb/AppImage/.rpm downloads now listed. Also iOS and Slack (Team Bots have their own Slack handle). The same thread syncs across devices. |
| **Standout features** | - **Follow along:** "Ask a Bot to follow along as you complete a workflow once. It saves it as a routine and runs it on its own next time." Routines can also run on a schedule.<br>- **Multi-bot threads:** put several bots in one thread and they pass work between themselves.<br>- **Team Bots:** one shared bot per team, built from four parts: Context (files, instructions, skills), Plugins (Salesforce, Notion, GitHub and others, connected per person or per team), Credentials (for APIs without a plugin) and Memories. **Each user's conversations and memories stay private** while skills are shared.<br>- **Marketplace:** bots from the Grok Bot team and from the community, sorted into categories such as Engineering, Sales, Marketing, Design, Personal, Recruiting and Ops.<br>- **Cursor integration:** bots launch Cursor Cloud Agents for code fixes. |
| **Computer model** | **All of a user's bots share ONE persistent cloud computer** (files, browser, logins). "Isolation is per user, not per Grok Bot." [primary FAQ] |
| **Security** | Cursor SSO, auth and privacy mode. Encryption in transit and at rest, plus a training opt-out. "Auto Review" for sensitive actions. Enterprise customers get DLP, certs, proxies, network controls, and Action Recording (off by default, 90-day logs, shell commands scrubbed) [secondary]. |
| **Pricing** | Individual plans: **Premium $30/mo, Super $100/mo (3.5× usage), Ultra $200/mo (12× usage)**. Grok Bot is also included in Teams and Enterprise plans. Each plan includes weekly usage, and **overage is billed at token cost**. At launch it was bundled with SuperGrok and Cursor Pro/Teams plans [primary]. |
| **Limits** | Grok Bot has its own usage pool. Allowance sizes are not published. Enterprise access is through sales. |
| **Links** | https://x.ai/news/introducing-grok-bot · https://x.ai/bot · https://x.ai/news/team-bots · https://x.ai/bot/marketplace |

### 1.2 OpenAI dots (the "GPT dots" the owner mentioned)

| | |
|---|---|
| **Real name** | **dots** (lowercase, "your dot"), launched in **"Introducing dots"** on **2026-09-29** [primary]. Tagged *ChatGPT* / *ChatGPT Work*. |
| **What it is** | "Remarkably capable, always-on agents built to handle everything." A dot is a persistent agent in ChatGPT that takes ongoing responsibility for goals and keeps working between conversations. |
| **Models** | GPT‑6 Astra. GPT‑6.1 Terra was added on 2026-11-03, and a dot can use different models for different parts of a job. |
| **Core concepts** | Primary dot (one per user, named, with a character or pet avatar and a handle like `@you-agentname`), its own cloud computer and browser, plugins (4,000+ apps), proactive research, Custom Rules, auto-review, Activity View, scheduled tasks, and **specialist dots** (enterprise pilots). |
| **Where it runs** | ChatGPT web, the desktop app (macOS and Windows) and mobile (iOS and Android). Not on mobile web. Also Slack and Teams. **Texting over iMessage/RCS** is in beta (US, Canada and Mexico, Pro only) through Linq. Voice calls work from the mobile app. |
| **Standout features** | - **Proactive research:** in the background, the dot scans connected apps with **read-only** tools and forms memories and suggestions.<br>- **Local computer:** you can optionally connect your own laptop, or several computers. The dot then uses local files and your local browser "when its cloud browser is blocked".<br>- **Delegation:** it delegates to Codex cloud environments and ChatGPT Work.<br>- **Custom Rules:** each action is set to one of four behaviors: *act without asking*, *act if pre-approved*, *ask first*, or *hand off to you*. Some actions, like password changes, always stay with the human.<br>- **Activity View** with In progress, Scheduled and Completed.<br>- Saved passwords are used without being exposed to the model.<br>- **Microsoft Agent 365** integration for specialist dots. |
| **Multi-agent** | Not yet. "Over time, we envision teams of dots working together." Each member gets **one personal dot**. Dots can't join group texts. |
| **Memory** | A dot inherits ChatGPT memory and adds its own, including memories from connected apps. You can **only delete the dot's own memories by deleting the dot**, which is a transparency gap. |
| **Pricing** | Your first dot is included in **Pro** and **Business Premium** with a monthly work allowance. In the future you'll be able to buy more dots or more speed and capacity. Enterprise pays flat rates by work type or by consumption. Enterprise preview is free 2026-11-04 → 2026-11-18, and **billing for all enabled dots starts 2026-11-18**. Codex and Work tasks a dot delegates are billed separately [primary help center]. Pro is commonly cited as "from $100/mo" [secondary]. |
| **Limits** | No EEA, Switzerland or UK on Pro. EU access is on Business and Enterprise only. No standalone email address for the dot at launch. A dot can't call you. Not available with UAE data residency. |
| **Links** | https://openai.com/index/introducing-dots/ · https://help.openai.com/en/articles/20001530-getting-started-with-your-dot · https://help.openai.com/en/articles/20001554-managing-dots-in-chatgpt-workspaces |

### 1.3 Meta Muse

| | |
|---|---|
| **Real name / launch** | **Muse**, "The World's First Personal AI Agent Built for Everyone". Launched **2026-09-08** in the US. A 2026-09-23 event added Realtime Avatar video calls, macOS app control, a dedicated agent email address, wake-word access on glasses, and the Muse Charm device [primary post updated 2026-11-10; event details are secondary]. **Muse Wonder** (October 2026) is the underlying frontier model for Muse, with "Active Memory" and "Active Focus". |
| **What it is** | A consumer-first personal agent that "doesn't just answer questions, it actually does the work". It runs on **Muse Secure VM**, an isolated cloud machine with its own browser that holds the agent, your data and stored credentials. |
| **Core concepts** | Muse Secure VM. **Sentinel**, a separate, system-isolated agent that must approve anything Muse sends to the internet. Credential handling where Muse uses logins without seeing passwords. An **audit trail** of what it did and plans to do. **Muse Confidential VM**, coming later, encrypts the VM with a user-held key. |
| **Where it runs** | iOS, Android, muse.ai and WhatsApp. AI glasses are coming soon. macOS app control was announced 2026-09-23. |
| **Standout features** | - Commerce: Link by Stripe with one-time cards, with Shop Pay and 1Password coming.<br>- Per-app access levels, with read access separated from write access.<br>- Proactive suggestions.<br>- Long-running work that continues after you close the app.<br>- "Forget this" memory control. |
| **Multi-agent** | None for users. The only second agent is Sentinel, used for safety. |
| **Pricing** | "Free for most needs, with subscription plans for heavier use" [primary]. Plans are $20 and $100/mo with no ads, and revenue is meant to come from transaction fees [secondary: Wikipedia]. |
| **Controversies** | Amazon blocked Muse on 2026-09-21. On 2026-09-22, reports said some calls were completed by humans. In October 2026 a shared-chat exposure was found and the sharing feature was suspended [secondary: Wikipedia, which flags possible LLM-written text]. |
| **Links** | https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/ · https://research.meta.ai/blog/muse-wonder |

### 1.4 Anthropic: Claude Tag (team, Slack) and Claude Duet (personal)

**Claude Tag**, launched 2026-06-23 [primary]
- **What it is:** one shared, always-on @Claude teammate per Slack channel. Anyone in the channel can hand it work, and others can pick up where someone left off.
- **How it works:** it builds memory from the channels it follows, scoped by admins. It can schedule its own tasks and work for hours or days.
- **Ambient mode:** it flags relevant information and follows up on stalled threads.
- **Separate identities:** admins can set up different Claude identities per use, for example sales and engineering.
- **Where it runs:** Slack only. It replaced the old Claude in Slack app.
- **Admin and spend controls:** admins scope tools and data per org, workspace or channel. They see an activity log of every action and who requested it. Spend is capped at the org and channel level. Admins can't read individual DMs.
- **Availability and model:** beta on Team and Enterprise only, with an introductory launch credit. Runs on Opus 4.8.
- Links: https://www.anthropic.com/news/introducing-claude-tag · https://claude.com/docs/claude-tag/overview

**Claude Duet**, launched 2026-10-21 as a research preview [primary]
- **What it is:** a proactive personal agent that sends a morning brief, takes tasks, keeps working after you leave, and asks before acting.
- **How it works:** it has its own VM and browser and 6,000+ connectors [secondary].
- **Hard approvals:** it asks before sending messages, paying, signing documents or deleting anything. Some actions are blocked even with approval, such as trading securities or moving money between accounts.
- **Where it runs:** web (claude.ai), iOS and Android.
- **Availability and pricing:** US waitlist on Pro, Max and Ultra plans (sources disagree on Ultra). Included at no extra cost, and background work counts against plan limits.
- **Limits:** it can't show you its browser and doesn't call or text other people.
- **Model:** Opus 5.5.
- Links: https://claude.com/resources/articles/claude-duet · https://support.claude.com/en/articles/17631495-get-started-with-claude-duet

### 1.5 Google Gemini agent and coworker agents

| | |
|---|---|
| **Launch** | Announced at Gemini at Work 2026. The blog post is dated **2026-10-09** and press reports say 2026-10-08. Private preview, with wider availability planned for select Workspace Business and Enterprise plans [primary + secondary]. |
| **What it is** | One universal work agent with one prompt box and one API. **Coworker agents** are persistent, role-based agents with **their own Workspace identity**: an `@agents.company.com` email address, a calendar, Drive and a directory entry. You add them to Chat spaces, @mention them, or tag them in Doc comments, and their edits show under their own name. |
| **Standout features** | - **Temporary sub-agents** that run for hours or days, each with its own identity.<br>- **Four memory types:** session, semantic, procedural (skills it writes itself) and episodic.<br>- **Agent Sandbox and Agent Gateway**, an AI firewall between agents.<br>- **Multi-model:** Gemini plus Anthropic Claude, with Smart Routing by cost.<br>- **Any MCP server**, plus a skills registry and an enterprise tools registry.<br>- **Per-project spend caps** that pause the agent when reached. |
| **Where it runs** | Web, iOS, Android, Windows and Mac desktop, CLI, Workspace, Microsoft 365, Slack, and headless embedding. |
| **Pricing** | Not published. Google says it won't charge a per-seat license for coworker agents [secondary: Futurum]. |
| **Link** | https://cloud.google.com/blog/products/ai-machine-learning/welcome-to-gemini-at-work-2026 |

### 1.6 Manus Cue [secondary only]
- **Launch:** 2026-09-28, alongside Manus 2.0.
- **What it is:** a standalone personal-agent app.
- **Features:** each agent gets its own **email address, phone number, wallet (with a budget) and computer**. Cue supports **group chats with several agents and a shared goal**, and purchases are tap-to-approve through Stripe Link.
- **Platforms:** web and desktop, with iOS pending.
- **Pricing:** unclear.
- **Context:** Meta's acquisition of Manus was cancelled in April 2026.
- Not verified against a Manus primary page.

### 1.7 Microsoft Agent 365: governance, not a teammate
- **Launch:** GA on 2026-05-01 [primary].
- **What it is:** a control plane that inventories, governs and secures agents from any vendor, including OpenAI's specialist dots.
- **Pricing:** $15 per user per month on its own, or included in Microsoft 365 E7 at $99 per user per month.
- **Identity:** autonomous agent identity through Entra Agent ID was still in preview at GA [secondary].
- **Why it matters:** enterprises will expect BotDesk bots to be governable, with an inventory, audit logs and identities.
- Link: https://www.microsoft.com/en-us/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/

### 1.8 Open source

Stars were taken from the GitHub API on 2026-11-11.

**Direct open-source Grok Bot / dots / Muse clones**, all created after 2026-08-11:

| Project | License | Stars | Notes |
|---|---|---|---|
| [milind-soni/OpenMausBot](https://github.com/milind-soni/OpenMausBot) | Apache-2.0 | 21,142 | Desktop chat app for Mac, Windows and Ubuntu. Each bot is a local Claude or Codex agent with its own model, cloud computer and apps. Bring your own agent. Sponsored by inference providers. **Biggest clone.** |
| [elie222/rakazo](https://github.com/elie222/rakazo) | Apache-2.0 | 7,926 | **Closest to BotDesk's plan.** Self-hosted; web, desktop, iOS and Android; routines on a schedule, email or webhook; memory; computer use; private or shared team computers; Docker, cloud or local sandboxes; group chats with @mentions; subagents; any model with your own keys; MCP; shareable "Pages" dashboards. |
| [Anil-matcha/suparagent](https://github.com/Anil-matcha/suparagent) | Apache-2.0 | 7,023 | Named AI coworkers with memory, routines, isolated computers and an "Ask first" approval mode. Self-host or a hosted version. Bring your own engine. Still early. |
| [opencoredev/akeru-bot](https://github.com/opencoredev/akeru-bot) | MIT | 132 | Fork of T3 Code. Local-first desktop, web and mobile clients. |
| [wolfqing/OpenSuperBot](https://github.com/wolfqing/OpenSuperBot) (was OpenGrokBot) | MIT | 124 | One container per bot. Any OpenAI-compatible model. |

**Personal-agent and runtime platforms:**

| Project | License | Stars | Relevance |
|---|---|---|---|
| [openclaw/openclaw](https://github.com/openclaw/openclaw) | MIT | 394,349 | The dominant open-source personal agent. It runs on your hardware and meets you in 20+ chat channels (Slack, Teams, WhatsApp, iMessage and others), with native apps. Models and harnesses are swappable plugins. **A possible integration target or a competitor.** |
| [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | MIT | 262,672 | "The agent that grows with you." Self-improving personal agent. |
| [iOfficeAI/AionUi](https://github.com/iOfficeAI/AionUi) | Apache-2.0 | 34,218 | A 24/7 "cowork" desktop app over OpenClaw, Hermes, Claude Code, Codex and 20+ other CLIs, where you can team agents together. |
| [kortix-ai/CompanyOS](https://github.com/kortix-ai/CompanyOS) (was Suna) | **Elastic-2.0, not OSI** | 20,654 | Multiplayer agents and "company as code". Sovereign hosting. |
| [agent0ai/agent-zero](https://github.com/agent0ai/agent-zero) | MIT | 19,830 | General agent framework with its own Linux environment. |
| [eigent-ai/eigent](https://github.com/eigent-ai/eigent) | Apache-2.0 | 15,806 | Open-source "cowork desktop" built on a CAMEL multi-agent workforce. |
| [agentscope-ai/AgentTeams](https://github.com/agentscope-ai/AgentTeams) | Apache-2.0 | 5,988 | Multi-agent OS where humans and agents share **Matrix rooms**. A good reference for group chat between humans and bots. |

**Computer-use and sandbox building blocks:**

| Project | License | Stars |
|---|---|---|
| [browser-use/browser-use](https://github.com/browser-use/browser-use) | MIT | 120,718 |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | MIT | 93,239 |
| [bytedance/UI-TARS-desktop](https://github.com/bytedance/UI-TARS-desktop) | Apache-2.0 | 39,597 |
| [trycua/cua](https://github.com/trycua/cua), with cross-OS sandboxes for computer use | MIT | 32,196 |
| [simular-ai/Agent-S](https://github.com/simular-ai/Agent-S) | Apache-2.0 | 12,943 |
| [e2b-dev/open-computer-use](https://github.com/e2b-dev/open-computer-use) | Apache-2.0 | 2,410 |

**Memory, orchestration and UI:**

| Project | License | Stars |
|---|---|---|
| [mem0ai/mem0](https://github.com/mem0ai/mem0), which BotDesk already plans to use | Apache-2.0 | 68,817 |
| [letta-ai/letta](https://github.com/letta-ai/letta) | Apache-2.0 | 25,420 |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | MIT | 60,777 |
| [LibreChat](https://github.com/LibreChat-AI/LibreChat) | MIT | 46,990 |
| [assistant-ui](https://github.com/assistant-ui/assistant-ui) | MIT | 13,069 |

Workflow tools with non-OSI or "fair-code" licenses: n8n (210k stars), Dify (161k stars, modified Apache) and Activepieces (25k stars, mixed MIT/EE).

---

## 2. Feature matrix

Legend:
- ✅ = shipped
- 🟡 = partial, preview or limited
- ❌ = no
- ? = unknown
- For BotDesk: **v1** = planned for v1, **later** = planned after v1

| Feature | Grok Bot | OpenAI dots | Meta Muse | Claude Tag / Duet | Gemini coworker agents | Rakazo (OSS) | **BotDesk (planned)** |
|---|---|---|---|---|---|---|---|
| Own cloud computer | ✅ one per user, shared by all bots | ✅ per dot; can also use your laptop | ✅ Secure VM | ❌ Tag / ✅ Duet VM | 🟡 sandbox, not a desktop | ✅ private or shared, Docker, cloud or local | **v1** sandbox per bot or shared, pluggable provider |
| Browser / computer use | ✅ | ✅ | ✅ | 🟡 Duet only; can't show you its browser | ? not described | ✅ | **v1** browser; full desktop **later** |
| Integrations / MCP | ✅ plugins, credentials, Cursor | ✅ 4,000+ plugins | 🟡 a few apps plus commerce | ✅ admin-chosen tools; Duet has 6k+ connectors | ✅ any MCP plus a registry | ✅ thousands plus MCP | **v1** MCP-first plus OAuth connectors |
| Approvals | ✅ Auto Review | ✅ Custom Rules (4 modes) plus auto-review | ✅ Sentinel | 🟡 Tag via admin scoping / ✅ Duet | 🟡 policies and RBAC | ✅ | **v1** per-action policy (allow, ask, block) |
| Group chat, bots plus humans | ✅ | 🟡 Slack/Teams channels; single dot | ❌ | ✅ Slack channels | ✅ Chat spaces, Docs | ✅ | **v1** |
| Orchestrator bot | ✅ Chief of Staff | ❌ teams "coming" | ❌ | ❌ | ✅ temporary sub-agents | ✅ delegation | **v1** chief-of-staff template |
| Memory | ✅ per user plus shared skills | ✅ but opaque; deleting means deleting the dot | ✅ with "forget" | ✅ channel-scoped | ✅ four types | ✅ | **v1** mem0, viewable and editable |
| Routines / learn by watching | ✅ follow along | 🟡 learns from feedback; no recording | ❌ | ❌ | 🟡 procedural memory | 🟡 routines, no watching | **v1** text routines; watch-and-record **later** |
| Proactive triggers and schedules | ✅ | ✅ proactive research plus schedules | ✅ suggestions | ✅ ambient plus self-scheduling / Duet morning brief | ✅ | ✅ schedule, email, webhook | **v1** cron plus webhooks; proactive nudges **later** |
| Marketplace / templates | ✅ Marketplace | ❌ | ❌ | ❌ | 🟡 skills registry | ❌ | **v1** built-in templates; community marketplace **later** |
| Teams / admin | ✅ Teams, Enterprise, audit | ✅ workspace admin, Agent 365 | ❌ consumer | ✅ Tag admin, spend caps, logs | ✅ RBAC, gateway, audit | 🟡 | **v1** orgs, roles, audit log, spend caps |
| Self-host | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | **v1** |
| Bring your own model keys | ❌ Grok only | ❌ OpenAI only | ❌ Meta only | ❌ Claude only | 🟡 Gemini plus Claude, chosen by Google | ✅ | **v1** all major providers plus OpenAI-compatible |
| Apps: web / desktop / mobile | 🟡 no web; desktop (Mac, Windows, Linux) plus iOS | ✅ web, desktop, mobile, Slack, Teams, SMS | 🟡 mobile, web, WhatsApp | 🟡 Slack / Duet web plus mobile | ✅ all plus CLI | ✅ web, desktop, iOS, Android | web **v1**; desktop and mobile **later** |
| Slack / Teams presence | ✅ Team Bots in Slack | ✅ | ❌ (WhatsApp) | ✅ Slack | ✅ Slack, Teams | ? | **later** (Slack first) |
| Open source | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ Apache-2.0 | ✅ **MIT** |

---

## 3. Where BotDesk can win

1. **A real "team of bots" in open source.** Grok Bot is the only commercial product with multi-bot threads and a chief of staff. OpenAI, Meta and Anthropic all ship *one* agent per person. BotDesk should make orgs, group threads and a chief of staff the default, not an add-on. Many open-source clones are single-user desktop apps. **Multi-tenant teams from day one** is BotDesk's clearest gap to fill.
2. **MIT license plus a supported self-host path.** Every big vendor is closed and cloud-only. Strong open-source rivals either use Apache-2.0 or fall back to non-OSI licenses (Kortix Elastic-2.0, n8n, Dify). MIT plus a one-command Docker or Helm deploy appeals to regulated teams that can't send credentials to xAI, OpenAI or Meta. Muse's Amazon block and shared-chat leak show why.
3. **Any model, routed by cost.** Every vendor locks you to its own models. Gemini's Smart Routing shows that routing pays off. BotDesk can route by task (cheap model for triage, frontier model for hard steps) using org keys or the user's own keys.
4. **Transparent, editable memory.** You can only wipe a dot's own memories by deleting the dot. BotDesk can show every memory, its source, its scope (personal, bot, team) and who can see it, with edit, forget and export. Grok's model of per-user private memory plus shared team skills is the right shape to copy.
5. **Cost control and visibility down to the cent.** Grok bills overage "at token cost" against allowances it doesn't publish. Dots billing started 2026-11-18 with little clarity. BotDesk can show a live cost per job and per bot, budgets per bot, team and org, and pause-on-cap like Gemini and Claude Tag. That turns "your bots meter their own usage" into a feature.
6. **Pluggable, isolated computers.** Grok Bots share one computer per user. That makes handoffs easy, but a prompt-injected bot can reach every login. BotDesk can offer per-bot isolation by default, with opt-in sharing, on E2B, Daytona, cua, Docker or local backends.
7. **Policy-as-code approvals and a full audit trail.** Combine dots' four rule modes with Muse's separate Sentinel approver and Grok's action recording. Version the policies, make them reviewable and exportable (to a SIEM, or later to Agent 365), so security teams can sign off.
8. **An open marketplace of portable bot definitions.** Grok's marketplace is closed and Grok-only. A BotDesk bot can be a portable file (instructions, skills, MCP servers, routines, policies) that you share through Git and install on any BotDesk. The format could also interoperate with OpenClaw and other agent skills.
9. **Meet users where they already chat.** Dots, Claude Tag and Team Bots all live in Slack, and OpenClaw covers 20+ channels. BotDesk can ship a web app first and a Slack or Teams bridge next. That beats Grok Bot, which has no web client at all.

## 4. Scope: what v1 needs to be credible, and what can wait

**Must have in v1.** Without these, BotDesk won't read as a Grok Bot alternative:
- Named bots with role, instructions, model, tools and avatar, created from templates such as Chief of Staff, Inbox, Research and Engineering.
- Threads and group chats with humans and bots, @mentions, and handoffs between bots. One chief-of-staff bot that delegates.
- **Jobs that run in the background** and survive closing the app, with live status (in progress, scheduled, done) and a way to stop or redirect them.
- **A cloud computer per bot** (at least a sandboxed browser plus a filesystem) that you can watch live and **take over to sign in**.
- **Approvals:** a per-action policy (allow, ask, block) and an inbox of pending approvals with the exact action previewed.
- Integrations through **MCP** plus a few first-party OAuth connectors: Gmail or Google Workspace, Slack, GitHub, Calendar and Notion.
- **Memory** through mem0, scoped to user, bot and team, with a UI to view, edit and forget.
- **Schedules and triggers** (cron, webhook, email-in) and a run history for each one.
- Orgs, members, roles, org-level and personal model keys, and multiple model providers.
- **Usage and cost metering** per bot and job, plus budget caps.
- An audit log of everything bots did.
- Self-host with Docker Compose, plus the hosted SaaS version.

**Later (v1.x to v2):**
- "Follow along": record a human's workflow (browser events plus screen) and turn it into an editable routine.
- Proactive behavior: read-only background scanning, nudges on stalled threads, a morning brief.
- A community marketplace and a portable bot format.
- Electron desktop app with local-computer access. Expo mobile app with push notifications for approvals.
- Slack and Teams bridges, so a bot has a handle in channels. Email and SMS identities for bots.
- Voice calls.
- A separate guard model that approves outbound actions, like Sentinel.
- Full desktop sandboxes for Windows and macOS.
- Enterprise features: SSO/SAML, SCIM, DLP, network egress policies, SIEM export.
- Wallets and spending with budgets (Muse and Cue style). Do this last, because payments carry high risk.

---

## 5. Sources

**Primary (vendor pages, read 2026-11-11)**
- Grok Bot launch: https://x.ai/news/introducing-grok-bot
- Grok Bot product, pricing and FAQ: https://x.ai/bot
- Team Bots: https://x.ai/news/team-bots
- Grok Bot Marketplace: https://x.ai/bot/marketplace
- Grok Bot for Enterprise (the page wouldn't render; details came from search snippets): https://x.ai/news/grok-bot-for-enterprise
- OpenAI, "Introducing dots": https://openai.com/index/introducing-dots/
- OpenAI Help, "Getting started with your dot": https://help.openai.com/en/articles/20001530-getting-started-with-your-dot
- OpenAI Help, "Managing dots in ChatGPT workspaces" (not read; content came from search snippets): https://help.openai.com/en/articles/20001554-managing-dots-in-chatgpt-workspaces
- Meta, "Introducing Muse": https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/
- Meta, Muse Wonder: https://research.meta.ai/blog/muse-wonder
- Anthropic, "Introducing Claude Tag": https://www.anthropic.com/news/introducing-claude-tag
- Claude Tag docs: https://claude.com/docs/claude-tag/overview
- Anthropic, "Introducing Claude Duet": https://claude.com/resources/articles/claude-duet
- Claude Duet help article: https://support.claude.com/en/articles/17631495-get-started-with-claude-duet
- Google Cloud, Gemini at Work 2026: https://cloud.google.com/blog/products/ai-machine-learning/welcome-to-gemini-at-work-2026
- Microsoft, Agent 365 GA: https://www.microsoft.com/en-us/security/blog/2026/05/01/microsoft-agent-365-now-generally-available-expands-capabilities-and-integrations/
- GitHub repos listed in section 1.8. Stars and licenses came from `gh api repos/<name>`. Kortix's license was read from its LICENSE file.

**Secondary (used only where flagged)**
- Muse on Wikipedia (dates, $20/$100 pricing, Amazon block, data leak): https://en.wikipedia.org/wiki/Muse_(AI_agent)
- Grok Bot enterprise controls: https://aiweekly.co/alerts/xai-opens-grok-bot-to-enterprises-with-new-audit-controls
- Grok Bot vs. dots, Pro pricing: https://kingy.ai/blog/grok-bot-vs-openai-dots/
- Gemini agent pricing comments: https://futurumgroup.com/insights/google-collapses-enterprise-ai-into-a-single-gemini-agent-at-gemini-at-work-2026/
- Gemini agent launch: https://www.cnbc.com/2026/10/08/google-cloud-introduces-gemini-agent-for-work-as-ai-race-heats-up.html
- Claude Duet launch: https://www.macrumors.com/2026/10/21/anthropic-claude-duet/
- Manus Cue: https://www.testingcatalog.com/manus-2-0-launches-with-studio-cloud-computer-and-cue/
- Manus Cue (French): https://siecledigital.fr/2026/09/30/separee-de-meta-manus-revient-avec-des-agents-ia-capables-de-telephoner-et-de-payer/
- OpenAI "Aeon" rumor, unconfirmed and not used: https://aiidelist.com/blog/openai-aeon-grok-bot-personal-agent-devday-2026

## Unverified or open questions
- Grok Bot's weekly usage allowance size, and the exact date it moved from SuperGrok bundling to the $30/$100/$200 plans.
- Exact Pro and Business Premium prices for dots. The "Managing dots in workspaces" admin article was not read in full.
- Muse's paid tier prices. The only source is Wikipedia, and Meta's page says only "subscription plans".
- Manus Cue pricing and platforms. No primary source was found.
- Google coworker-agent pricing and GA date.
- Whether Grok Bot's "Chief of Staff" is a special orchestration feature or just a marketplace template with delegation instructions. The product page lists it as one of the "Give each Bot a job" roles.
