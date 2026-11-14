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

## Consequences for earlier docs

Accepted ADRs are not rewritten; read their hosted-service wording through this one:

- [ADR 0001](0001-product-scope-and-deployment.md) decision 1: self-hosted only; the backend stays multi-tenant.
- [ADR 0005](0005-job-queue-and-scaling.md) decision 7 ("before hosted sign-ups open") and stage 3 ("hosted service"): read as a large self-hosted install serving teams that don't trust each other.
- [ADR 0006](0006-repo-structure-plugins-and-project.md) decision 5: every install uses its own Google OAuth client; there is no public hosted app to put through Google's verification and CASA.
