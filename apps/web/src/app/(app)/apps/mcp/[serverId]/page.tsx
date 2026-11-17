import { Suspense } from "react";
import type { Metadata } from "next";
import { McpToolReviewScreen } from "@/features/apps/mcp-tool-review-screen";

export const metadata: Metadata = { title: "Review tools" };

/* Connect apps → an MCP server → Review tools. Dynamic params resolve inside <Suspense>. */
export default function McpToolReviewPage({ params }: PageProps<"/apps/mcp/[serverId]">) {
  return <Suspense fallback={null}>{params.then(({ serverId }) => <McpToolReviewScreen serverId={serverId} />)}</Suspense>;
}
