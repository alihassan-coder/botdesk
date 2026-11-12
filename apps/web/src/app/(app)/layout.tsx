import { AppShell } from "@/features/shell/app-shell";

/** Every page in the app sits inside the shell: bot sidebar on the left, the page on the right. */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return <AppShell>{children}</AppShell>;
}
