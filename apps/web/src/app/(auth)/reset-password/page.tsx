import { Suspense } from "react";
import type { Metadata } from "next";
import { ResetPasswordScreen } from "@/features/auth/reset-password-screen";

export const metadata: Metadata = { title: "Choose a new password" };

/* The token comes from the emailed link (?token=…). Search params resolve inside <Suspense>. */
export default function ResetPasswordPage({ searchParams }: PageProps<"/reset-password">) {
  return (
    <Suspense fallback={null}>
      {searchParams.then(({ token }) => (
        <ResetPasswordScreen token={typeof token === "string" && token ? token : null} />
      ))}
    </Suspense>
  );
}
