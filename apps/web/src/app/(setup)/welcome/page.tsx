import type { Metadata } from "next";
import { WelcomeScreen } from "@/features/onboarding/welcome-screen";

export const metadata: Metadata = { title: "Set up your organization" };

export default function WelcomePage() {
  return <WelcomeScreen />;
}
