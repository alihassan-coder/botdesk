import { cn } from "@/lib/utils";
import { initialOf } from "@/lib/format";

/** An organization's mark: its first letter on the brand colour. */
export function OrgAvatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("grid size-7 shrink-0 place-items-center rounded-lg bg-brand text-[13px] font-semibold text-brand-foreground", className)}
    >
      {initialOf(name)}
    </span>
  );
}
