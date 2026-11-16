import { Ban, Check, CircleAlert, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { TaskStatus } from "@/data/types";
import { cn } from "@/lib/utils";

const LABEL: Record<TaskStatus, string> = {
  queued: "Queued",
  working: "Working…",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

const LOOK: Record<TaskStatus, string> = {
  queued: "border-border text-muted-foreground",
  working: "bg-brand/10 text-brand",
  done: "bg-success/12 text-emerald-700 dark:text-emerald-300",
  failed: "bg-destructive/10 text-destructive dark:bg-destructive/20",
  cancelled: "border-border text-muted-foreground",
};

/**
 * Where a Task is. Each status has its own word and icon, not just a colour. Keyed by status,
 * so a change fades the new badge in (opacity only when motion is reduced). While working, a
 * small dot breathes; with reduced motion it stays still.
 */
export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  return (
    <Badge
      key={status}
      variant={status === "queued" || status === "cancelled" ? "outline" : "secondary"}
      className={cn(
        "transition-[opacity,scale] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] starting:scale-95 starting:opacity-0 motion-reduce:starting:scale-100",
        LOOK[status],
      )}
    >
      <StatusIcon status={status} />
      {LABEL[status]}
    </Badge>
  );
}

function StatusIcon({ status }: { status: TaskStatus }) {
  switch (status) {
    case "queued":
      return <Clock aria-hidden />;
    case "working":
      return <span aria-hidden data-working-dot className="mx-0.5 size-1.5 rounded-full bg-current motion-safe:animate-pulse" />;
    case "done":
      return <Check aria-hidden />;
    case "failed":
      return <CircleAlert aria-hidden />;
    case "cancelled":
      return <Ban aria-hidden />;
  }
}
