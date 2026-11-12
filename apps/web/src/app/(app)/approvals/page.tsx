import type { Metadata } from "next";
import { ComingSoon } from "@/features/shell/coming-soon";

export const metadata: Metadata = { title: "Approvals" };

export default function ApprovalsPage() {
  return (
    <ComingSoon
      title="Approvals"
      description="Every action waiting for a yes, from every bot, in one inbox. For now, approve them inside each chat."
    />
  );
}
