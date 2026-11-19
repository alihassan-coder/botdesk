import { useTransition } from "react";
import { X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { actions, useBot, useUser } from "@/data/store";
import type { Participant, Thread } from "@/data/types";

/** Takes someone out of the group at once (adding them back is just as quick); a refusal shows as a toast. */
export function RemoveMemberButton({ thread, member }: { thread: Thread; member: Participant }) {
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
      className="tap-target text-muted-foreground opacity-100 hover:text-foreground focus-visible:opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover/member:opacity-100"
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
