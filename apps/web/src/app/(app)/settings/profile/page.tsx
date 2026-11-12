import type { Metadata } from "next";
import { ProfileSettings } from "@/features/settings/profile-settings";

export const metadata: Metadata = { title: "Profile · Settings" };

export default function ProfileSettingsPage() {
  return <ProfileSettings />;
}
