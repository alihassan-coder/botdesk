import type { Metadata } from "next";
import { RoutinesScreen } from "@/features/routines/routines-screen";

export const metadata: Metadata = { title: "Routines" };

export default function RoutinesPage() {
  return <RoutinesScreen />;
}
