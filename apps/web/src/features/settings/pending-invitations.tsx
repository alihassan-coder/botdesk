import { useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { TimeAgo } from "@/components/time-ago";
import { actions } from "@/data/store";
import type { Invitation } from "@/data/types";
import { SettingsSection } from "./settings-shell";

/** Invites sent but not accepted yet. Revoking one makes its link stop working. */
export function PendingInvitations({ invitations }: { invitations: Invitation[] }) {
  return (
    <SettingsSection title="Pending invites" description="People you invited who haven't joined yet.">
      <ul className="flex flex-col divide-y rounded-2xl border">
        {invitations.map((invite) => (
          <PendingInvitation key={invite.id} invite={invite} />
        ))}
      </ul>
    </SettingsSection>
  );
}

function PendingInvitation({ invite }: { invite: Invitation }) {
  const [revoking, startRevoking] = useTransition();

  const revoke = () =>
    startRevoking(async () => {
      const result = await actions.revokeInvitation(invite.id);
      if (!result.ok) toast.error(result.error);
    });

  return (
    <li className="flex items-center gap-3 p-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{invite.email}</p>
        <p className="truncate text-xs text-muted-foreground">
          <span className="capitalize">{invite.role}</span> · invited <TimeAgo iso={invite.createdAt} />
        </p>
      </div>
      <Button variant="ghost" size="sm" onClick={revoke} disabled={revoking}>
        Revoke
      </Button>
    </li>
  );
}
