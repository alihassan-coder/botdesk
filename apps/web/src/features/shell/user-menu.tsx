import Link from "next/link";
import { useTheme } from "next-themes";
import { ChevronsUpDown, LogOut, Monitor, Moon, Settings, Sun } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSidebar } from "@/components/ui/sidebar";
import { actions, useCurrentUser } from "@/data/store";
import { MemberAvatar } from "@/features/bots/bot-avatar";

/** You, at the bottom of the sidebar: theme switch, settings and sign out. */
export function UserMenu() {
  const user = useCurrentUser();
  const { theme, setTheme } = useTheme();
  const { isMobile, setOpenMobile } = useSidebar();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger aria-label={`Account: ${user.name}`} className="flex w-full items-center gap-3 rounded-[10px] p-2 text-left outline-none hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-1">
        <MemberAvatar name={user.name} size="sm" className="size-8" />
        <span className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
          <span className="block truncate text-sm font-medium">{user.name}</span>
          <span className="block truncate text-xs text-muted-foreground">{user.email}</span>
        </span>
        <ChevronsUpDown className="size-4 text-muted-foreground group-data-[collapsible=icon]:hidden" />
      </DropdownMenuTrigger>

      <DropdownMenuContent side="top" align="start" className="w-60">
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
          <DropdownMenuRadioItem value="light"><Sun /> Light</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark"><Moon /> Dark</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system"><Monitor /> System</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings/profile" onClick={() => isMobile && setOpenMobile(false)}><Settings /> Settings</Link>
        </DropdownMenuItem>
        {/* AuthGate notices and takes you to the sign-in page. */}
        <DropdownMenuItem onSelect={actions.signOut}>
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
