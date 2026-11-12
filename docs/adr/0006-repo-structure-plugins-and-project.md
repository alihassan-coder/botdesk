# 0006: Repo structure, plugin SDK, contributions and releases

- Status: accepted
- Date: 2026-11-12
- Based on: [architecture review](../architecture/review-2026-11-12.md) (findings 8, 9, 10, 15) and [repo-structure.md](../architecture/repo-structure.md)

## Context

BotDesk is open source. People should be able to find their way around the repo, write a plugin without reading the core, and send a change without legal paperwork. The plugin platform also has to stay safe when outsiders write plugins.

## Decisions

1. **Repo layout** as in [repo-structure.md](../architecture/repo-structure.md):
   - `apps/` holds runnable things: web, api (with the worker inside), desktop and mobile later.
   - `packages/` holds shared libraries, including `packages/plugin-sdk` (Python).
   - `plugins/` holds the built-in plugins (Gmail first).
   - `deploy/` holds docker compose and deployment files.
   - `docs/` holds the documentation.
2. **One Python workspace:** a root **uv workspace** (one lockfile for api, SDK and plugins), set up when the plugin SDK arrives (build step 3).
3. **The plugin SDK is its own package**, published to PyPI separately, so plugin authors depend on the SDK, not on the whole app. Plugins are found through Python **entry points**, but only those on an admin **allowlist** are loaded. Manifests are generated from code and validated.
4. **Third-party plugins in v1: MCP servers only.**
   - We set an MCP tool's risk; the server's own hints are ignored.
   - Every MCP tool starts as `external-send` and asks.
   - Tool lists are hash-pinned, so a changed tool needs re-approval.
   - HTTP (no-code) plugins come after MCP. The sandbox tier (third-party Python code) comes only if someone needs it.
5. **Gmail:** self-hosters use their own Google OAuth client first. A public hosted service needs Google's restricted-scope verification and security assessment (CASA). We budget time and money for it before a hosted launch.
6. **Contributions: DCO sign-off** (`git commit -s`), no CLA. Branch protection on `main` is turned on when a second regular contributor joins.
7. **Releases: release-please.** One version for the app, and a separate version for the plugin SDK on PyPI. It reads the Conventional Commit messages we already use.

## Consequences

- CONTRIBUTING.md asks for `git commit -s`. A DCO check runs in CI once outside contributions start.
- New top-level folders (`packages/`, `plugins/`, `deploy/`) appear when their first real content does, not before.
