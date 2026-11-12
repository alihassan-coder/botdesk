import type { Metadata } from "next";
import { OrganizationSettings } from "@/features/settings/organization-settings";

export const metadata: Metadata = { title: "Organization · Settings" };

export default function OrganizationSettingsPage() {
  return <OrganizationSettings />;
}
