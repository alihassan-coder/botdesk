import type { Metadata } from "next";
import { ApprovalsScreen } from "@/features/approvals/approvals-screen";

export const metadata: Metadata = { title: "Approvals" };

export default function ApprovalsPage() {
  return <ApprovalsScreen />;
}
