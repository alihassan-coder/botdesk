import { redirect } from "next/navigation";

/** /settings opens the first section. */
export default function SettingsPage() {
  redirect("/settings/profile");
}
