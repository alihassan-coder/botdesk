import type { Metadata } from "next";
import { ComingSoon } from "@/features/shell/coming-soon";

export const metadata: Metadata = { title: "Routines" };

export default function RoutinesPage() {
  return (
    <ComingSoon
      title="Routines"
      description="Jobs your bots repeat on a schedule. For now, see and switch a bot's routines in its details pane."
    />
  );
}
