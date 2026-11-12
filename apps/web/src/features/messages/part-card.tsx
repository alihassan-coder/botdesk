import { cn } from "@/lib/utils";

/** The shared frame for every card inside a chat (work log, computer task, approval…). */
export function PartCard({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("w-full max-w-[560px] rounded-2xl border bg-card p-3.5 text-sm", className)} {...props} />;
}
