import { SidebarTrigger } from "@/components/ui/sidebar";

/** Top bar for full pages (not chats): a sidebar button where the sidebar can hide, then the title. */
export function PageHeader({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
      <SidebarTrigger className="-ml-1 md:hidden" />
      <h1 className="text-base font-semibold tracking-tight">{title}</h1>
      <div className="ml-auto flex items-center gap-2">{children}</div>
    </header>
  );
}
