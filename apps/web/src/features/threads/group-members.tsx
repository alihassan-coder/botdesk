import { useTransition } from "react";
import { X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { pluralize } from "@/lib/format";
import { actions, useBot, useCanChangeLead, useUser } from "@/data/store";
import type { Participant, Thread } from "@/data/types";
import { BotAvatar, MemberAvatar } from "@/features/bots/bot-avatar";
import { BOT_STATUS } from "@/features/bots/bot-status";
import { AddToGroupDialog } from "./add-to-group-dialog";
import { GroupLead } from "./group-lead";
import { RenameGroupDialog } from "./rename-group-dialog";

/**
 * The details pane for a group chat: its name, lead bot, then everyone in it, people first, then
 * bots. Its creator, owners and admins (the same rule as the lead) rename it and add or remove
 * people and bots.
 */
export function GroupMembers({ thread }: { thread: Thread }) {
  const canManage = useCanChangeLead(thread);
  const people = thread.participants.filter((p) => p.type === "user");
  const bots = thread.participants.filter((p) => p.type === "bot");
  // A group keeps at least one person, so the last one has no Remove.
  const removable = (p: Participant) => canManage && (p.type === "bot" || people.length > 1);

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
            {removable(m) && <RemoveButton thread={thread} member={m} />}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Takes someone out of the group at once (adding them back is just as quick); a refusal shows as a toast. */
function RemoveButton({ thread, member }: { thread: Thread; member: Participant }) {
  const bot = useBot(member.type === "bot" ? member.id : undefined);
  const user = useUser(member.type === "user" ? member.id : undefined);
  const name = bot?.name ?? user?.name ?? "them";
  const [removing, startRemoving] = useTransition();

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={`Remove ${name} from the group`}
      title={`Remove ${name}`}
      disabled={removing}
      className="text-muted-foreground opacity-100 hover:text-foreground focus-visible:opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover/member:opacity-100"
      onClick={() =>
        startRemoving(async () => {
          const result = await actions.removeFromGroup(thread.id, member);
          if (!result.ok) toast.error(result.error);
        })
      }
    >
      <X />
    </Button>
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
