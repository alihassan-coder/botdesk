import { SetupShell } from "@/features/onboarding/setup-shell";

/** Pages for signed-in people that stand alone, outside the app shell (first-time setup). */
export default function SetupLayout({ children }: LayoutProps<"/">) {
  return <SetupShell>{children}</SetupShell>;
}
