"use client";

import { useCurrentUser, useInvitations, useUsers } from "@/data/store";
import { InviteDialog } from "./invite-dialog";
import { MemberRow } from "./member-row";
import { PendingInvitations } from "./pending-invitations";
import { SettingsSection } from "./settings-shell";

/** Settings → Members: who's in the org, what they can do, and invites still waiting. */
export function MembersSettings() {
  const users = useUsers();
  const invitations = useInvitations();
  const me = useCurrentUser();
  // Members can see the team; only owners and admins change it.
  const canManage = me.role !== "member";

  return (
    <div className="flex flex-col gap-8">
      <SettingsSection
        title="Members"
        description="Admins manage bots, keys and security. Members chat with bots and approve their own."
        action={canManage ? <InviteDialog /> : undefined}
      >
        <ul className="flex flex-col divide-y rounded-2xl border">
          {users.map((u) => (
            <MemberRow key={u.id} member={u} isMe={u.id === me.id} canManage={canManage} />
          ))}
        </ul>
      </SettingsSection>
      {canManage && invitations.length > 0 && <PendingInvitations invitations={invitations} />}
    </div>
  );
}
