import type { AccountConnection, ConnectionOwner } from "@/data/types";
import { sitePath } from "./next-path";

/** How a self-hoster sets up Google sign-in (Connect apps links it when a connector isn't set up). */
export const GOOGLE_SETUP_GUIDE_URL = "https://github.com/alihassan-coder/botdesk/blob/main/docs/self-hosting/google-oauth.md";

const ACCESS_LABELS: Record<string, string> = {
  read: "Read only",
  full: "Read, organise, draft and send",
};

/** "read" → "Read only"; an access level we have no words for is shown capitalised. */
export function accessLabel(level: string): string {
  return ACCESS_LABELS[level] ?? `${level.charAt(0).toUpperCase()}${level.slice(1)}`;
}

/** What the OAuth callback page says, from the API's redirect (`?result=…&code=…`). */
export type CallbackOutcome = { ok: true; connectorId: string | null } | { ok: false; message: string };

const CALLBACK_ERRORS: Record<string, string> = {
  denied: "You cancelled signing in, so nothing was connected.",
  expired: "That sign-in took too long or was already used. Start again from Connect apps.",
  "not-configured": "This app isn't set up on this server yet. Ask whoever runs BotDesk to add its sign-in client.",
  "signed-out": "Sign in to BotDesk first, then connect the app again.",
  forbidden: "You can't connect an account for that owner any more.",
  failed: "Couldn't finish connecting the app. Try again.",
};

export function callbackOutcome(result: string | null, code: string | null, connector: string | null): CallbackOutcome {
  if (result === "connected") return { ok: true, connectorId: connector };
  return { ok: false, message: CALLBACK_ERRORS[code ?? ""] ?? CALLBACK_ERRORS.failed };
}

/*
 * Signing in with a provider takes the whole tab away, and the API sends it back to
 * /apps/callback. The page Connect was pressed on (a bot's DM, Connect apps) is remembered for
 * this tab (sessionStorage) so the callback page can go back there.
 */
const OAUTH_RETURN_KEY = "botdesk.oauthReturnTo";
/** Connect apps: where the callback page goes back to by default. */
export const CONNECT_APPS = "/apps";

/** Remember where to come back to after the provider's sign-in. */
export function rememberOAuthReturn(path: string): void {
  try {
    sessionStorage.setItem(OAUTH_RETURN_KEY, path);
  } catch {} // storage blocked: the callback page falls back to Connect apps
}

/** Where the callback page goes back to: the remembered page, or Connect apps. */
export function readOAuthReturn(): string {
  let saved: string | null = null;
  try {
    saved = sessionStorage.getItem(OAUTH_RETURN_KEY);
  } catch {}
  return oauthReturnPath(saved);
}

/** Only a page on this site (lib/next-path.ts), never the callback page itself; else Connect apps. */
export function oauthReturnPath(saved: string | null): string {
  const path = sitePath(saved, CONNECT_APPS);
  return path.startsWith("/apps/callback") ? CONNECT_APPS : path;
}

/** "Back to …" the page it goes back to. */
export function returnLabel(path: string): string {
  if (path === CONNECT_APPS || path.startsWith(`${CONNECT_APPS}?`)) return "Connect apps";
  if (path.startsWith("/chat/")) return "the chat";
  if (path === "/") return "your chats";
  return "where you were";
}

/** Who a connection belongs to, as the Connect dialog's owner choice. */
export function ownerOf(connection: AccountConnection): ConnectionOwner {
  if (connection.ownerKind === "bot" && connection.ownerBotId) return { kind: "bot", botId: connection.ownerBotId };
  return connection.ownerKind === "org" ? { kind: "org" } : { kind: "member" };
}

/** "Just you", the bot's name, "Organization", or "Another member" (admins see that others' exist). */
export function ownerLabel(connection: AccountConnection, currentUserId: string, botName: (botId: string) => string | undefined): string {
  if (connection.ownerKind === "org") return "Organization";
  if (connection.ownerKind === "bot") return (connection.ownerBotId && botName(connection.ownerBotId)) || "A bot";
  return connection.ownerUserId === currentUserId ? "Just you" : "Another member";
}

/**
 * The accounts a bot's plugin may work through: active ones of that connector that are yours,
 * this bot's own, or the organization's. Another member's account is never offered.
 */
export function bindableConnections(accounts: AccountConnection[], connectorId: string, botId: string, currentUserId: string): AccountConnection[] {
  return accounts.filter(
    (c) =>
      c.connectorId === connectorId &&
      c.status === "active" &&
      (c.ownerKind === "org" || (c.ownerKind === "bot" && c.ownerBotId === botId) || (c.ownerKind === "member" && c.ownerUserId === currentUserId)),
  );
}
