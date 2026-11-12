import { useState } from "react";
import Link from "next/link";
import { Inbox, Plug, Repeat, Search, Settings, Store } from "lucide-react";
import { Kbd } from "@/components/ui/kbd";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInput,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { usePendingApprovalCount } from "@/data/store";
import { ThreadList } from "./thread-list";
import { UserMenu } from "./user-menu";
import { WorkspaceHeader } from "./workspace-header";

/** Pages reached from the bottom of the sidebar. */
const FOOTER_LINKS = [
  { href: "/routines", label: "Routines", icon: Repeat },
  { href: "/apps", label: "Connect apps", icon: Plug },
  { href: "/marketplace", label: "Marketplace", icon: Store },
  { href: "/settings", label: "Settings", icon: Settings },
];

/** The left column: brand and "+", search, approvals, your bots and groups, then app pages and you. */
export function AppSidebar() {
  const pendingApprovals = usePendingApprovalCount();
  const [query, setQuery] = useState("");
  const { isMobile, setOpenMobile } = useSidebar();

  // On phones the sidebar is a sheet; close it once the user picks something.
  const closeOnPhone = () => isMobile && setOpenMobile(false);

  return (
    <Sidebar collapsible="offcanvas">
      <SidebarHeader className="gap-3 px-3 pt-3">
        <WorkspaceHeader onNavigate={closeOnPhone} />
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <SidebarInput
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search bots and groups"
            aria-label="Search bots and groups"
            className="h-9 rounded-[10px] pr-12 pl-8"
          />
          <Kbd className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2" title="Open the command palette">
            ⌘K
          </Kbd>
        </div>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild>
              <Link
                href="/approvals"
                onClick={closeOnPhone}
                // The count badge sits outside the link visually; say it in the link's name for screen readers.
                aria-label={pendingApprovals > 0 ? `Approvals, ${pendingApprovals} waiting` : "Approvals"}
              >
                <Inbox /> Approvals
              </Link>
            </SidebarMenuButton>
            {pendingApprovals > 0 && <SidebarMenuBadge className="text-brand">{pendingApprovals}</SidebarMenuBadge>}
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent className="px-2 py-2">
        <ThreadList query={query} onNavigate={closeOnPhone} />
      </SidebarContent>

      <SidebarFooter className="px-2 pb-3">
        <SidebarMenu>
          {FOOTER_LINKS.map(({ href, label, icon: Icon }) => (
            <SidebarMenuItem key={href}>
              <SidebarMenuButton asChild>
                <Link href={href} onClick={closeOnPhone}>
                  <Icon /> {label}
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
        <UserMenu />
      </SidebarFooter>
    </Sidebar>
  );
}
