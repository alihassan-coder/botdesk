import type { Metadata } from "next";
import { MemorySettings } from "@/features/settings/memory-settings";

export const metadata: Metadata = { title: "Memory · Settings" };

export default function MemorySettingsPage() {
  return <MemorySettings />;
}
