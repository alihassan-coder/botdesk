import { CircleAlert } from "lucide-react";

/** Why the form didn't go through, read out by screen readers as soon as it appears. */
export function FormError({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="flex items-center gap-2 rounded-xl bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
      <CircleAlert className="size-4 shrink-0" /> {children}
    </p>
  );
}
