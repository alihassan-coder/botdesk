import { AuthLayout } from "@/features/auth/auth-layout";

/** Sign in, sign up and password reset share the brand panel + form layout. */
export default function AuthPagesLayout({ children }: LayoutProps<"/">) {
  return <AuthLayout>{children}</AuthLayout>;
}
