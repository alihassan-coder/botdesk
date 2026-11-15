import { BotAvatar, MemberAvatar } from "@/features/bots/bot-avatar";
import { cn } from "@/lib/utils";
import type { BotAvatarColor, BotStatus } from "@/data/types";

/** Someone in the chat who can be @mentioned. */
export interface MentionOption {
  type: "bot" | "user";
  id: string;
  handle: string;
  name: string;
  /** Bots only: role, avatar colour and status. */
  role?: string;
  color?: BotAvatarColor;
  status?: BotStatus;
}

export const MENTION_LIST_ID = "mention-suggestions";
export const mentionOptionId = (option: MentionOption) => `mention-${option.type}-${option.id}`;

/**
 * The list that opens above the message box while you type an @handle.
 * Focus stays in the box: arrows move the highlight, Enter or Tab picks, Escape closes.
 */
export function MentionSuggestions({
  options,
  activeIndex,
  onPick,
  onHover,
}: {
  options: MentionOption[];
  activeIndex: number;
  onPick: (option: MentionOption) => void;
  onHover: (index: number) => void;
}) {
  return (
    <div className="absolute inset-x-0 bottom-full z-20 mb-2 overflow-hidden rounded-2xl border bg-popover text-popover-foreground shadow-lg">
      <p className="px-3 pt-2.5 pb-1 text-xs font-medium text-muted-foreground">Mention someone in this chat</p>
      <ul id={MENTION_LIST_ID} role="listbox" aria-label="People and bots to mention" className="max-h-64 overflow-y-auto p-1.5">
        {options.map((option, index) => (
          <li
            key={mentionOptionId(option)}
            id={mentionOptionId(option)}
            role="option"
            aria-selected={index === activeIndex}
            // Keep focus (and the caret) in the message box.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onPick(option)}
            onMouseMove={() => onHover(index)}
            className={cn(
              "flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-2.5 py-1.5",
              index === activeIndex && "bg-accent text-accent-foreground",
            )}
          >
            {option.type === "bot" && option.color ? (
              <BotAvatar name={option.name} color={option.color} status={option.status} size="sm" />
            ) : (
              <MemberAvatar name={option.name} size="sm" />
            )}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{option.name}</span>
              <span className="block truncate text-xs text-muted-foreground">
                @{option.handle}
                {option.type === "bot" ? ` · ${option.role || "Bot"}` : " · Teammate"}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
