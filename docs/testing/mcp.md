# Manual test: MCP servers (slice 7.2)

How to check by hand that a remote MCP server's tools become bot tools. About 15 minutes. Background: [ADR 0012](../adr/0012-mcp-servers.md), [backend guide](../backend/README.md#mcp-servers).

## Before you start

- The API and web running against the API (`pnpm dev`), migrated (`cd apps/api && pnpm db:migrate`; the revision is `73107c948749`).
- A model key (org or instance) if you want a real bot to call the tool; without one, check the tool calls with the stand-in or skip step 4.
- Signed in as an **owner or admin**, and a second account that is a **member** of the same organization.
- An MCP server that speaks **Streamable HTTP over https**. Pick one:
  - **A public one, no key:** DeepWiki's `https://mcp.deepwiki.com/mcp` (tools to read GitHub repos' docs). Any public Streamable HTTP server works.
  - **A public one with a key:** GitHub's `https://api.githubcopilot.com/mcp/` with header `Authorization` and value `Bearer <a GitHub token>`.
  - **Your own, on your machine:** BotDesk only speaks https, and refuses private addresses by default. Either expose the local server through an https tunnel (`cloudflared tunnel --url http://localhost:8001` or ngrok; the tunnel's address is public, so no setting is needed), or serve it with a certificate your machine trusts and set `ALLOW_PRIVATE_MCP_URLS=true` in `apps/api/.env` (restart the API). Plain `http://` is always refused.

## Checklist

1. **Add (owner/admin).** Connect apps → *MCP servers* → **Add server**. Name it, paste the URL (and the header name + key if it needs one) → **Add server**.
   - [ ] The dialog says "Connecting…", closes, and a toast says to turn it on in a bot's Tools.
   - [ ] The server is listed with its URL and "N tools"; "What bots can do" lists each tool as *Sends outside your org*.
   - [ ] Reload the page: the key appears nowhere (the API returns only the header's name).
2. **Refused addresses.** Add again with `https://127.0.0.1/mcp`, then `http://example.com/mcp`.
   - [ ] Each shows an error in the dialog and nothing is added. (With `ALLOW_PRIVATE_MCP_URLS=true` the first is allowed through the guard and fails only if nothing answers.)
3. **Bot's Tools.** Open a bot → Tools.
   - [ ] The server is there by its name, **off**, every tool marked *Sends outside your org*. Switch it on.
4. **A call asks and taints.** With the bot on *Ask before acting*, ask it in its DM to use one of the server's tools (e.g. with DeepWiki: "@bot use the MCP tool to tell me what the repo facebook/react is about").
   - [ ] An approval card appears for the MCP tool; approve it.
   - [ ] The bot answers from the tool's result. Ask it to do something risky next (another MCP call, or a demo *send email*): it asks again, and the card says the chat has read outside text.
   - [ ] On *Autonomous*, the first MCP call runs without asking; after its result, the next MCP call asks (taint).
5. **Refresh.** Back on Connect apps → **Refresh** on the server.
   - [ ] A toast says the tools are up to date; the tool count matches the server. (Changed-tool refusal is covered by `tests/test_mcp_servers.py`; to see it by hand with your own server, change a tool's description, ask the bot to call it: it fails with "This tool changed on the server; an admin must refresh it." Refresh, then it works again.)
6. **Members.** Sign in as the member → Connect apps.
   - [ ] The server and its tools are listed; there is no Add server, Refresh or Remove.
7. **Remove (owner/admin).** **Remove** → confirm.
   - [ ] The server is gone, and so is its entry in every bot's Tools.

## Not in this slice

MCP sign-in with OAuth (7.3); choosing which tools are available and changing their risk, and a "tools changed" badge with a diff (7.4); the automatic drift check at run start.
