import type { Metadata } from "next";
import { MembersSettings } from "@/features/settings/members-settings";

export const metadata: Metadata = { title: "Members · Settings" };

export default function MembersSettingsPage() {
  return <MembersSettings />;
}
