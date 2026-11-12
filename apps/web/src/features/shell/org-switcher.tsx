import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Building2, Check, ChevronsUpDown, Plus, UserPlus } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { actions, useOrg, useOrgs } from "@/data/store";
import { OrgAvatar } from "./org-avatar";
import { PLAN_LABEL } from "./plan";

const RAIL_HIDDEN = "group-data-[collapsible=icon]:hidden";

/**
 * Your organization at the top of the sidebar: switch to another one you belong to,
 * manage it, invite people. Switching goes home, since the open chat belongs to the old org.
 */
export function OrgSwitcher({ onNavigate }: { onNavigate?: () => void }) {
  const org = useOrg();
  const orgs = useOrgs();
  const router = useRouter();

  const switchTo = (orgId: string) => {
    if (orgId === org.id) return;
    void actions.switchOrg(orgId);
    onNavigate?.();
    router.push("/");
  };

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
        {orgs.map((o) => (
          <DropdownMenuItem key={o.id} onSelect={() => switchTo(o.id)} aria-current={o.id === org.id ? "true" : undefined}>
            <OrgAvatar name={o.name} className="size-6 rounded-md text-xs" />
            <span className="min-w-0 flex-1 truncate">{o.name}</span>
            {o.id === org.id ? <Check /> : <span className="text-xs text-muted-foreground capitalize">{o.role}</span>}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings/organization" onClick={onNavigate}><Building2 /> Manage organization</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings/members" onClick={onNavigate}><UserPlus /> Invite people</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => toast("Creating more organizations arrives soon. Ask a teammate for an invite meanwhile.")}>
          <Plus /> New organization
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
