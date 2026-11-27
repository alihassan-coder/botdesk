/**
 * Official remote MCP servers, each hosted by the company whose app it reaches (checked against
 * each vendor's docs on 2026-11-27). Connect apps offers them as presets for Add MCP server.
 */

/** How a catalogue server lets BotDesk in. */
export type McpCatalogueSignIn =
  /** One-click sign-in: BotDesk registers itself with the server. */
  | { kind: "oauth" }
  /** A token sent in a header on every request. `where` says how to get one. */
  /** `valuePrefix` (like "Bearer ") goes in front of the pasted key when it isn't there already. */
  | { kind: "key"; header: string; valuePrefix?: string; valuePlaceholder: string; token: string; where: string }
  /**
   * Sign-in through an OAuth app the admin creates first in the vendor's console (`console`),
   * given BotDesk's redirect URI; its client ID and secret are pasted into the dialog.
   */
  | { kind: "oauth-client"; console: string; steps: string };

export interface McpCatalogueEntry {
  /** Also the id ConnectorLogo draws its brand mark for. */
  id: string;
  name: string;
  publisher: string;
  url: string;
  /** What it lets bots do, in one line. */
  description: string;
  signIn: McpCatalogueSignIn;
  docsUrl: string;
}

const GOOGLE_DOCS = "https://developers.google.com/workspace/guides/configure-mcp-servers";
const google = {
  kind: "oauth-client",
  console: "Google Cloud",
  steps: "In the Google Cloud console, create an OAuth client of type Web application and add the redirect URI below to it.",
} as const;

export const MCP_CATALOGUE: readonly McpCatalogueEntry[] = [
  { id: "gmail", name: "Gmail", publisher: "Google", url: "https://gmailmcp.googleapis.com/mcp/v1", description: "Search and read email, and draft replies.", signIn: google, docsUrl: GOOGLE_DOCS },
  { id: "google-calendar", name: "Google Calendar", publisher: "Google", url: "https://calendarmcp.googleapis.com/mcp/v1", description: "Check free time, and find, create and move events.", signIn: google, docsUrl: GOOGLE_DOCS },
  { id: "google-drive", name: "Google Drive", publisher: "Google", url: "https://drivemcp.googleapis.com/mcp/v1", description: "Find and read files and folders.", signIn: google, docsUrl: GOOGLE_DOCS },
  {
    id: "slack", name: "Slack", publisher: "Slack", url: "https://mcp.slack.com/mcp", description: "Search messages, read channels and threads, and post replies.",
    signIn: { kind: "oauth-client", console: "Slack", steps: "Create a Slack app, add the redirect URI below to it, and have a workspace admin approve it." },
    docsUrl: "https://docs.slack.dev/ai/mcp-server",
  },
  {
    id: "github", name: "GitHub", publisher: "GitHub", url: "https://api.githubcopilot.com/mcp/", description: "Search code, and read and update issues and pull requests.",
    signIn: {
      kind: "key", header: "Authorization", valuePrefix: "Bearer ", valuePlaceholder: "ghp_…", token: "personal access token",
      where: "Create one in GitHub under Settings, Developer settings, Personal access tokens, and paste it here (BotDesk adds “Bearer ” in front).",
    },
    docsUrl: "https://github.com/github/github-mcp-server",
  },
  { id: "linear", name: "Linear", publisher: "Linear", url: "https://mcp.linear.app/mcp", description: "Find, create and update issues and projects.", signIn: { kind: "oauth" }, docsUrl: "https://linear.app/docs/mcp" },
  { id: "notion", name: "Notion", publisher: "Notion", url: "https://mcp.notion.com/mcp", description: "Search, read and edit pages and databases.", signIn: { kind: "oauth" }, docsUrl: "https://developers.notion.com/docs/mcp" },
  {
    id: "atlassian", name: "Jira & Confluence", publisher: "Atlassian", url: "https://mcp.atlassian.com/v2/mcp", description: "Search and update Jira issues and Confluence pages.",
    signIn: { kind: "oauth" }, docsUrl: "https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/",
  },
  { id: "sentry", name: "Sentry", publisher: "Sentry", url: "https://mcp.sentry.dev/mcp", description: "Look into errors and issues, with their stack traces.", signIn: { kind: "oauth" }, docsUrl: "https://mcp.sentry.dev" },
  { id: "stripe", name: "Stripe", publisher: "Stripe", url: "https://mcp.stripe.com", description: "Look up customers and payments, and create invoices and refunds.", signIn: { kind: "oauth" }, docsUrl: "https://docs.stripe.com/mcp" },
  {
    id: "hubspot", name: "HubSpot", publisher: "HubSpot", url: "https://mcp.hubspot.com/", description: "Find and update contacts, companies and deals.",
    signIn: { kind: "oauth-client", console: "HubSpot", steps: "Create an MCP auth app on HubSpot's developer platform and add the redirect URI below to it." },
    docsUrl: "https://developers.hubspot.com/mcp",
  },
  {
    id: "asana", name: "Asana", publisher: "Asana", url: "https://mcp.asana.com/v2/mcp", description: "Find, create and update tasks and projects.",
    signIn: { kind: "oauth-client", console: "Asana", steps: "Create an MCP app in Asana's developer console and add the redirect URI below to it." },
    docsUrl: "https://developers.asana.com/docs/using-asanas-mcp-server",
  },
];

/**
 * The form two addresses of one server share: the scheme and host lowercased, no trailing
 * slash, no fragment. The path keeps its case (servers may tell paths apart by it).
 */
export function normalizeMcpUrl(url: string): string {
  const trimmed = url.trim();
  try {
    const u = new URL(trimmed);
    return `${u.protocol}//${u.host}${u.pathname.replace(/\/+$/, "")}${u.search}`;
  } catch {
    return trimmed.replace(/\/+$/, "").toLowerCase();
  }
}

const BY_URL = new Map(MCP_CATALOGUE.map((entry) => [normalizeMcpUrl(entry.url), entry]));

/** The catalogue server at this address, if it is one (an added server's brand mark, "Added"). */
export function catalogueEntryFor(url: string): McpCatalogueEntry | undefined {
  return BY_URL.get(normalizeMcpUrl(url));
}

/** "Sign in with Linear", "Needs a personal access token", "Needs an app you create in Google Cloud". */
export function signInLine({ publisher, signIn }: McpCatalogueEntry): string {
  switch (signIn.kind) {
    case "oauth":
      return `Sign in with ${publisher}`;
    case "key":
      return `Needs a ${signIn.token}`;
    case "oauth-client":
      return `Needs an app you create in ${signIn.console}`;
  }
}

/** A pasted key with the header's prefix ("Bearer ") in front, unless it already starts with it. */
export function withKeyPrefix(value: string, prefix: string | undefined): string {
  if (!prefix || value.toLowerCase().startsWith(prefix.toLowerCase())) return value;
  return prefix + value;
}
