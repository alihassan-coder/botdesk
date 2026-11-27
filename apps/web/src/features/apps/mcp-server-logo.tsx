import { ConnectorLogo, type ConnectorLogoSize } from "@/components/connector-logo";
import type { McpServer } from "@/data/types";
import { catalogueEntryFor } from "@/lib/mcp-catalogue";

/**
 * An MCP server's logo, always next to its name: the icon it sent in its handshake, else the
 * brand mark of the official server at its address (lib/mcp-catalogue.ts), else its initial.
 */
export function McpServerLogo({ server, size }: { server: Pick<McpServer, "name" | "url" | "pluginId" | "iconUrl">; size?: ConnectorLogoSize }) {
  const official = catalogueEntryFor(server.url);
  return <ConnectorLogo connectorId={official?.id ?? server.pluginId} name={server.name} iconUrl={server.iconUrl} size={size} decorative />;
}
