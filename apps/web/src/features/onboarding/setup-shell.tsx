"use client";

import { useApplySavedAccent } from "@/features/settings/accent";
import { AuthGate } from "@/features/shell/auth-gate";

/** First-time setup sits behind sign-in like the app, but without the sidebar: one thing to do. */
export function SetupShell({ children }: { children: React.ReactNode }) {
  useApplySavedAccent();
  return <AuthGate>{children}</AuthGate>;
}
