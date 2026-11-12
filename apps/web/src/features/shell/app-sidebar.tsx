import { useState } from "react";
import Link from "next/link";
import { Inbox, Plug, Repeat, Settings, Store } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
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
  { href: "/settings/profile", label: "Settings", icon: Settings },
];

/**
 * The left column: logo, organization, search and new; approvals; your bots and groups;
 * then app pages and you. Collapses to an icon rail (⌘B or Ctrl+B); on phones it's a sheet.
 */
export function AppSidebar() {
  const pendingApprovals = usePendingApprovalCount();
  const [query, setQuery] = useState("");
  const { isMobile, setOpenMobile } = useSidebar();

  // On phones the sidebar is a sheet; close it once the user picks something.
  const closeOnPhone = () => isMobile && setOpenMobile(false);

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="gap-3 px-3 pt-3 group-data-[collapsible=icon]:px-2">
        <WorkspaceHeader query={query} onQueryChange={setQuery} onNavigate={closeOnPhone} />
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild tooltip="Approvals">
              <Link
                href="/approvals"
                onClick={closeOnPhone}
                // The count badge sits outside the link visually; say it in the link's name for screen readers.
                aria-label={pendingApprovals > 0 ? `Approvals, ${pendingApprovals} waiting` : "Approvals"}
              >
                <Inbox /> <span>Approvals</span>
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
              <SidebarMenuButton asChild tooltip={label}>
                <Link href={href} onClick={closeOnPhone}>
                  <Icon /> <span>{label}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
        <UserMenu />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
