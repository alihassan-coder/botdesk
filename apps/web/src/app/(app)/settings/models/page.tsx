import type { Metadata } from "next";
import { ModelsSettings } from "@/features/settings/models-settings";

export const metadata: Metadata = { title: "Models & keys · Settings" };

export default function ModelsSettingsPage() {
  return <ModelsSettings />;
}
