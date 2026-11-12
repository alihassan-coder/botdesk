import type { Metadata } from "next";
import { UsageSettings } from "@/features/settings/usage-settings";

export const metadata: Metadata = { title: "Usage & budgets · Settings" };

export default function UsageSettingsPage() {
  return <UsageSettings />;
}
