import Link from "next/link";
import { toast } from "sonner";
import { Check, ChevronsUpDown, Plus, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useOrg } from "@/data/store";
import { BotdeskTile } from "./logo";

/**
 * Top of the sidebar: the brand tile, "botdesk" with your organisation underneath
 * (click to switch), and "+" to create a bot or a group.
 */
export function WorkspaceHeader({ onNavigate }: { onNavigate?: () => void }) {
  const org = useOrg();

  return (
    <div className="flex items-center gap-1">
      <DropdownMenu>
        <DropdownMenuTrigger className="flex min-w-0 flex-1 items-center gap-2.5 rounded-xl p-1 text-left outline-none hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring">
          <BotdeskTile />
          <span className="min-w-0 flex-1 leading-tight">
            <span className="block text-[15px] font-semibold tracking-[-0.03em]">botdesk</span>
            <span className="block truncate text-xs text-muted-foreground">{org.name}</span>
          </span>
          <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-60">
          <DropdownMenuLabel className="text-xs text-muted-foreground">Organizations</DropdownMenuLabel>
          <DropdownMenuItem>
            <span className="grid size-6 place-items-center rounded-md bg-muted text-xs font-semibold">{org.name[0]}</span>
            {org.name}
            <Check className="ml-auto" />
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => toast("Creating organizations arrives with accounts (API).")}>
            <Plus /> New organization
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <NewMenu onNavigate={onNavigate} />
    </div>
  );
}

/** "+": create a bot (from scratch or the marketplace) or start a group chat. */
function NewMenu({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="New bot or group">
          <Plus />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuItem asChild>
          <Link href="/bots/new" onClick={onNavigate}>
            <Plus /> New bot
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/marketplace" onClick={onNavigate}>
            <Users /> Hire from marketplace
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => toast("Group chats with an @mention picker arrive next.")}>
          <Users /> New group
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
