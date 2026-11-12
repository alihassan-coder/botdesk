import type { Metadata } from "next";
import { AppsScreen } from "@/features/apps/apps-screen";

export const metadata: Metadata = { title: "Connect apps" };

export default function AppsPage() {
  return <AppsScreen />;
}
