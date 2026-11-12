import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { makeHandle } from "@/lib/handle";
import { useBots, useModel } from "@/data/store";
import type { NewBotInput } from "@/data/store";
import { BotAvatar } from "./bot-avatar";
import { securityLabel } from "./security-levels";

/** What the new bot will look like, updating as you type: its card and the first thing it will say. */
export function BotPreview({ bot }: { bot: NewBotInput }) {
  const bots = useBots();
  const model = useModel(bot.modelId);
  const name = bot.name.trim() || "Your bot";
  const handle = makeHandle(name, bots.map((b) => b.handle));

  return (
    <div className="flex flex-col gap-4 rounded-2xl border bg-card p-5">
      <p className="text-xs font-medium text-muted-foreground">Preview</p>
      <div className="flex items-center gap-3">
        <BotAvatar name={name} color={bot.avatarColor} size="lg" status="idle" />
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold tracking-tight">{name}</p>
          <p className="truncate text-sm text-muted-foreground">
            {bot.role.trim() || "Role"} · @{handle}
          </p>
        </div>
      </div>

      <Bubble variant="muted" className="max-w-full">
        <BubbleContent className="rounded-2xl px-3.5 py-2 text-[14px]">
          Hi! I&apos;m {name}. {bot.description.trim() || bot.role.trim() || "Tell me what to do."} What should I work on first?
        </BubbleContent>
      </Bubble>

      <dl className="grid grid-cols-[92px_1fr] gap-x-3 gap-y-1.5 border-t pt-4 text-sm">
        <dt className="text-muted-foreground">Model</dt>
        <dd>{model?.name}</dd>
        <dt className="text-muted-foreground">Security</dt>
        <dd>{securityLabel(bot.securityLevel)}</dd>
        <dt className="text-muted-foreground">Budget</dt>
        <dd>${bot.monthlyBudgetUsd} a month</dd>
      </dl>
    </div>
  );
}
