import { SettingsShell } from "@/features/settings/settings-shell";

/** Every settings section shares the header and the section links. */
export default function SettingsLayout({ children }: LayoutProps<"/settings">) {
  return <SettingsShell>{children}</SettingsShell>;
}
