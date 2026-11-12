import { Calendar, Code, CreditCard, FileText, Mail, MessageSquare, Server, Users, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Connector } from "@/data/types";

/* Category icons instead of third-party logos: we don't ship other companies' brand assets. */
const ICON: Record<Connector["category"], LucideIcon> = {
  email: Mail,
  calendar: Calendar,
  chat: MessageSquare,
  dev: Code,
  docs: FileText,
  crm: Users,
  finance: CreditCard,
  mcp: Server,
};

export function ConnectorIcon({ category, className }: { category: Connector["category"]; className?: string }) {
  const Icon = ICON[category];
  return (
    <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl border bg-muted/50", className)}>
      <Icon className="size-5 text-muted-foreground" />
    </span>
  );
}
