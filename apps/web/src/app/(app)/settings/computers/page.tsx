import type { Metadata } from "next";
import { ComputersSettings } from "@/features/settings/computers-settings";

export const metadata: Metadata = { title: "Computers · Settings" };

export default function ComputersSettingsPage() {
  return <ComputersSettings />;
}
