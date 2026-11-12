import type { Metadata } from "next";
import { ComingSoon } from "@/features/shell/coming-soon";

export const metadata: Metadata = { title: "Connect apps" };

export default function AppsPage() {
  return (
    <ComingSoon
      title="Connect apps"
      description="Give your bots access to Gmail first, then more apps and any MCP server."
    />
  );
}
