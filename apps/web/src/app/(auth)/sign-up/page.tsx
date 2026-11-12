import type { Metadata } from "next";
import { SignUpScreen } from "@/features/auth/sign-up-screen";

export const metadata: Metadata = { title: "Create your account" };

export default function Page() {
  return <SignUpScreen />;
}
