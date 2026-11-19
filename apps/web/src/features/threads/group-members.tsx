import { pluralize } from "@/lib/format";
import { useBot, useCanChangeLead, useCurrentUser, useUser } from "@/data/store";
import type { Participant, Thread } from "@/data/types";
import { BotAvatar, MemberAvatar } from "@/features/bots/bot-avatar";
import { BOT_STATUS } from "@/features/bots/bot-status";
import { AddToGroupDialog } from "./add-to-group-dialog";
import { GroupLead } from "./group-lead";
import { LeaveGroupButton } from "./leave-group-button";
import { RemoveMemberButton } from "./remove-member-button";
import { RenameGroupDialog } from "./rename-group-dialog";

/**
 * The details pane for a group chat: its name, lead bot, then everyone in it, people first, then
 * bots. Its creator, owners and admins (the same rule as the lead) rename it and add or remove
 * people and bots. Anyone in it may leave it.
 */
export function GroupMembers({ thread }: { thread: Thread }) {
  const canManage = useCanChangeLead(thread);
  const me = useCurrentUser().id;
  const people = thread.participants.filter((p) => p.type === "user");
  const bots = thread.participants.filter((p) => p.type === "bot");
  // You don't remove yourself: you leave (the button at the foot).
  const removable = (p: Participant) => canManage && (p.type === "bot" || p.id !== me);

  return (
    <div className="flex flex-col gap-5 overflow-y-auto p-4">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-lg font-semibold tracking-tight">{thread.title}</h2>
          <p className="text-sm text-muted-foreground">
            {pluralize(people.length, "person", "people")} · {pluralize(bots.length, "bot")}
          </p>
        </div>
        {canManage && <RenameGroupDialog thread={thread} />}
      </div>
      {canManage && <AddToGroupDialog thread={thread} />}
      <GroupLead thread={thread} />
      <MemberSection title="People" thread={thread} members={people} removable={removable} />
      <MemberSection title="Bots" thread={thread} members={bots} removable={removable} />
      <LeaveGroupButton thread={thread} />
    </div>
  );
}

function MemberSection({
  title,
  thread,
  members,
  removable,
}: {
  title: string;
  thread: Thread;
  members: Participant[];
  removable: (p: Participant) => boolean;
}) {
  if (members.length === 0) return null;
  return (
    <section>
      <h3 className="mb-2 text-xs font-medium text-muted-foreground">{title}</h3>
      <ul className="flex flex-col gap-1">
        {members.map((m) => (
          <li key={m.id} className="group/member flex items-center gap-2">
            <span className="min-w-0 flex-1">{m.type === "bot" ? <BotMember id={m.id} /> : <PersonMember id={m.id} />}</span>
            {removable(m) && <RemoveMemberButton thread={thread} member={m} />}
          </li>
        ))}
      </ul>
    </section>
  );
}

function BotMember({ id }: { id: string }) {
  const bot = useBot(id);
  if (!bot) return null;
  return (
    <div className="flex items-center gap-3 py-1">
      <BotAvatar name={bot.name} color={bot.avatarColor} status={bot.status} />
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium">{bot.name}</span>
        <span className="block truncate text-xs text-muted-foreground">{BOT_STATUS[bot.status].label}</span>
      </span>
    </div>
  );
}

function PersonMember({ id }: { id: string }) {
  const user = useUser(id);
  if (!user) return null;
  return (
    <div className="flex items-center gap-3 py-1">
      <MemberAvatar name={user.name} />
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium">{user.name}</span>
        <span className="block truncate text-xs text-muted-foreground capitalize">{user.role}</span>
      </span>
    </div>
  );
}
