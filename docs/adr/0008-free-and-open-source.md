# 0008: BotDesk is free and open source, with no paid plans

- Status: accepted
- Date: 2026-11-13
- Changes: [ADR 0001](0001-product-scope-and-deployment.md) decision 1 (the hosted SaaS part)

## Context

ADR 0001 planned BotDesk as self-hosted and a hosted SaaS, and the code carried an organization `plan` ("self-hosted", "free", "pro", "team") that the sidebar and settings showed as "Free plan" or "Team plan". The owner decided that BotDesk is never a paid product.

## Decision

1. **BotDesk is MIT and free forever.** No paid plans, tiers, credits, seats or paid-only features.
2. **People bring their own AI keys** (Settings → Models & keys) and pay their AI provider directly. BotDesk never charges or resells model access.
3. **Organizations have no plan.** The `organizations.plan` column is dropped, `OrgOut` no longer has `plan`, and the web shows no plan label.
4. **Prices in the app are only what the AI provider charges**, for usage reports and budgets.
5. **Self-hosting is the way to run BotDesk.** The backend stays multi-tenant (organizations, roles), so one install can serve several teams.

## Trade-offs

- No revenue to pay for a hosted service, so there is none to sign up for.
- Budgets protect people's own provider bills, not a BotDesk quota.
