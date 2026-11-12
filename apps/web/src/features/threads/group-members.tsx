import { useBot, useUser } from "@/data/store";
import type { Participant, Thread } from "@/data/types";
import { BotAvatar, MemberAvatar } from "@/features/bots/bot-avatar";
import { BOT_STATUS } from "@/features/bots/bot-status";

/** The details pane for a group chat: everyone in it, people first, then bots. */
export function GroupMembers({ thread }: { thread: Thread }) {
  const people = thread.participants.filter((p) => p.type === "user");
  const bots = thread.participants.filter((p) => p.type === "bot");

  return (
    <div className="flex flex-col gap-5 overflow-y-auto p-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">{thread.title}</h2>
        <p className="text-sm text-muted-foreground">
          {people.length} people · {bots.length} bots
        </p>
      </div>
      <MemberSection title="People" members={people} />
      <MemberSection title="Bots" members={bots} />
    </div>
  );
}

function MemberSection({ title, members }: { title: string; members: Participant[] }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-medium text-muted-foreground">{title}</h3>
      <ul className="flex flex-col gap-1">
        {members.map((m) => (
          <li key={m.id}>{m.type === "bot" ? <BotMember id={m.id} /> : <PersonMember id={m.id} />}</li>
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
