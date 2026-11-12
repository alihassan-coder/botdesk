import Link from "next/link";
import { toast } from "sonner";
import { Plus, Search, SquarePen, Store, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Kbd } from "@/components/ui/kbd";
import { SidebarInput, SidebarTrigger } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useShortcut } from "@/hooks/use-shortcut";
import { openCommandPalette } from "@/features/command-palette/command-palette";
import { BotdeskLockup, BotdeskMark } from "./logo";
import { OrgSwitcher } from "./org-switcher";

/* Classes that only apply when the sidebar is collapsed to the icon rail. */
const RAIL_HIDDEN = "group-data-[collapsible=icon]:hidden";
const RAIL_ONLY = "hidden group-data-[collapsible=icon]:flex";

/**
 * Top of the sidebar, three rows: the botdesk logo and the collapse button; your
 * organization (switch, manage, invite); search and "new". Collapsed, each becomes one icon.
 */
export function WorkspaceHeader({ query, onQueryChange, onNavigate }: { query: string; onQueryChange: (q: string) => void; onNavigate?: () => void }) {
  const toggleShortcut = useShortcut("b");
  const searchShortcut = useShortcut("k");
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 px-1 group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:px-0">
        <Link href="/" onClick={onNavigate} className="flex items-center gap-2 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="botdesk home">
          <BotdeskLockup className={`h-[21px] ${RAIL_HIDDEN}`} />
          <BotdeskMark className={`size-[22px] ${RAIL_ONLY}`} />
        </Link>
        <Tooltip>
          <TooltipTrigger asChild>
            <SidebarTrigger className="ml-auto text-muted-foreground group-data-[collapsible=icon]:ml-0" />
          </TooltipTrigger>
          <TooltipContent side="right">
            Collapse or expand <Kbd>{toggleShortcut}</Kbd>
          </TooltipContent>
        </Tooltip>
      </div>

      <OrgSwitcher onNavigate={onNavigate} />

      <div className="flex items-center gap-1.5 group-data-[collapsible=icon]:flex-col">
        <div className={`relative flex-1 ${RAIL_HIDDEN}`}>
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <SidebarInput
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Search"
            aria-label="Search bots and groups"
            className="h-9 rounded-[10px] pr-16 pl-8"
          />
          <Kbd className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2">{searchShortcut}</Kbd>
        </div>
        <Button variant="ghost" size="icon-sm" className={RAIL_ONLY} onClick={openCommandPalette} aria-label="Search" aria-keyshortcuts="Control+K Meta+K">
          <Search />
        </Button>
        <NewMenu onNavigate={onNavigate} />
      </div>
    </div>
  );
}

/** New: create a bot, hire one from the marketplace, or start a group chat. */
function NewMenu({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="icon-sm" className="size-9 rounded-[10px] group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:border-transparent group-data-[collapsible=icon]:bg-transparent group-data-[collapsible=icon]:shadow-none dark:group-data-[collapsible=icon]:border-transparent dark:group-data-[collapsible=icon]:bg-transparent" aria-label="New">
              <SquarePen />
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="right">New bot or group</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem asChild>
          <Link href="/bots/new" onClick={onNavigate}><Plus /> New bot</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/marketplace" onClick={onNavigate}><Store /> Hire from marketplace</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => toast("Group chats with an @mention picker arrive next.")}>
          <Users /> New group
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
