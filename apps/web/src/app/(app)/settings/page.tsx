import type { Metadata } from "next";
import { ComingSoon } from "@/features/shell/coming-soon";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <ComingSoon
      title="Settings"
      description="Your profile, appearance, models and keys, security levels, members, usage and budgets. The theme switch is in your user menu now."
    />
  );
}
