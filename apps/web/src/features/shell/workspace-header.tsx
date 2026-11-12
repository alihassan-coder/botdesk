import Link from "next/link";
import { toast } from "sonner";
import { Building2, Check, ChevronsUpDown, Plus, Search, SquarePen, Store, UserPlus, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Kbd } from "@/components/ui/kbd";
import { SidebarInput, SidebarTrigger } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useOrg } from "@/data/store";
import { openCommandPalette } from "@/features/command-palette/command-palette";
import { BotdeskMark } from "./logo";
import { OrgAvatar } from "./org-avatar";
import { PLAN_LABEL } from "./plan";

/* Classes that only apply when the sidebar is collapsed to the icon rail. */
const RAIL_HIDDEN = "group-data-[collapsible=icon]:hidden";
const RAIL_ONLY = "hidden group-data-[collapsible=icon]:flex";

/**
 * Top of the sidebar, three rows: the botdesk logo and the collapse button; your
 * organization (switch, manage, invite); search and "new". Collapsed, each becomes one icon.
 */
export function WorkspaceHeader({ query, onQueryChange, onNavigate }: { query: string; onQueryChange: (q: string) => void; onNavigate?: () => void }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 px-1 group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:px-0">
        <Link href="/" onClick={onNavigate} className="flex items-center gap-2 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="botdesk home">
          <BotdeskMark weight={14} className="size-[22px]" />
          <span className={`text-[17px] font-semibold tracking-[-0.045em] ${RAIL_HIDDEN}`}>botdesk</span>
        </Link>
        <Tooltip>
          <TooltipTrigger asChild>
            <SidebarTrigger className="ml-auto text-muted-foreground group-data-[collapsible=icon]:ml-0" />
          </TooltipTrigger>
          <TooltipContent side="right">Collapse or expand · ⌘B</TooltipContent>
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
            className="h-9 rounded-[10px] pr-11 pl-8"
          />
          <Kbd className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2">⌘K</Kbd>
        </div>
        <Button variant="ghost" size="icon-sm" className={RAIL_ONLY} onClick={openCommandPalette} aria-label="Search (⌘K)">
          <Search />
        </Button>
        <NewMenu onNavigate={onNavigate} />
      </div>
    </div>
  );
}

/** Your organization: switch between orgs, manage it, invite people. */
function OrgSwitcher({ onNavigate }: { onNavigate?: () => void }) {
  const org = useOrg();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={`Organization: ${org.name}`}
        className="flex w-full items-center gap-2.5 rounded-xl border bg-background/70 p-1.5 pr-2 text-left shadow-xs outline-none hover:bg-background focus-visible:ring-2 focus-visible:ring-ring group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:border-0 group-data-[collapsible=icon]:bg-transparent group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:shadow-none"
      >
        <OrgAvatar name={org.name} />
        <span className={`min-w-0 flex-1 leading-tight ${RAIL_HIDDEN}`}>
          <span className="block truncate text-sm font-medium">{org.name}</span>
          <span className="block truncate text-xs text-muted-foreground">{PLAN_LABEL[org.plan]}</span>
        </span>
        <ChevronsUpDown className={`size-3.5 shrink-0 text-muted-foreground ${RAIL_HIDDEN}`} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="bottom" className="w-64">
        <DropdownMenuLabel className="text-xs text-muted-foreground">Organizations</DropdownMenuLabel>
        <DropdownMenuItem>
          <OrgAvatar name={org.name} className="size-6 rounded-md text-xs" />
          {org.name}
          <Check className="ml-auto" />
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings/organization" onClick={onNavigate}><Building2 /> Manage organization</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings/members" onClick={onNavigate}><UserPlus /> Invite people</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => toast("Creating organizations arrives with accounts on the API.")}>
          <Plus /> New organization
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** New: create a bot, hire one from the marketplace, or start a group chat. */
function NewMenu({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="icon-sm" className="size-9 rounded-[10px] group-data-[collapsible=icon]:size-8" aria-label="New">
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
