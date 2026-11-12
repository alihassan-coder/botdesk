import type { Metadata } from "next";
import { ComingSoon } from "@/features/shell/coming-soon";

export const metadata: Metadata = { title: "Marketplace" };

export default function MarketplacePage() {
  return (
    <ComingSoon
      title="Marketplace"
      description="Ready-made bots you can hire in one click, like an Inbox Manager or a Recruiter."
    />
  );
}
