import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { BotAvatarColor } from "@/data/types";
import { COLOR_CLASS } from "./bot-avatar";

const COLORS = Object.keys(COLOR_CLASS) as BotAvatarColor[];

/** A row of colour swatches for a bot's avatar. Works with the keyboard like a radio group. */
export function ColorPicker({ value, onChange }: { value: BotAvatarColor; onChange: (color: BotAvatarColor) => void }) {
  return (
    <div role="radiogroup" aria-label="Colour" className="flex flex-wrap gap-2">
      {COLORS.map((color) => {
        const selected = color === value;
        return (
          <button
            key={color}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={color}
            onClick={() => onChange(color)}
            className={cn(
              "grid size-8 place-items-center rounded-[10px] text-white outline-none transition-transform hover:scale-105 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              COLOR_CLASS[color],
              selected && "ring-2 ring-foreground ring-offset-2 ring-offset-background",
            )}
          >
            {selected && <Check className="size-4" />}
          </button>
        );
      })}
    </div>
  );
}
