# 0001 — Product scope and deployment model

- Status: accepted
- Date: 2026-11-11

## Decisions

0. **Product: an open-source Grok Bot** ([launch post](https://x.ai/news/introducing-grok-bot)). It's a team of always-on AI agents with their own cloud computers, approvals, group chats and routines. It's not a copy of the grok.com chat app.

1. **Deployment: self-hosted AND hosted SaaS.** The backend is multi-tenant from day one. Self-hosting is a docker-compose setup of the same code.
2. **Teams are a core feature.** We build in organizations/workspaces with members and roles, shared conversations and projects, and **agents** that belong to a team (custom AI personas with their own instructions, model, tools and memory scope).
3. **@mentions.** Users can mention teammates (`@ali`) and agents (`@researcher`) inside a chat. Mentioning an agent makes it reply; mentioning a person notifies them.
4. **Model keys: both.** Users can bring their own keys, and org admins can set org-wide keys. Usage is tracked per user and per org.
5. **Look: Grok's feel, BotDesk's identity.** Same dark, minimal mood, with our own logo and accent colour. We don't use any Grok/xAI trademarks or assets.
6. **Web first.** Next.js comes first. Desktop (Electron) and mobile (Expo) come later and reuse the same API.

## Consequences

- Every table that holds user content carries an `org_id`. Authorization checks org membership and role.
- A conversation can have multiple human participants and multiple agents, so messages record who sent them (user or agent).
- We need realtime events (new messages, typing, presence, streaming visible to everyone in the chat), not just one-user streaming.
