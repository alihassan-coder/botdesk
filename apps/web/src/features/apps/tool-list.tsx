import { ChevronRight } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { RiskClass } from "@/data/types";
import { RISK } from "@/features/approvals/risk";

/** What bots can do with an app or plugin, and how risky each action is. */
export function ToolList({ tools }: { tools: { name: string; label: string; risk: RiskClass }[] }) {
  return (
    <Collapsible className="group/tools">
      <CollapsibleTrigger className="tap-target flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground">
        <ChevronRight className="size-3.5 transition-transform group-data-[state=open]/tools:rotate-90" />
        What bots can do ({tools.length})
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-2 flex flex-col divide-y rounded-xl border text-sm">
          {tools.map((tool) => {
            const risk = RISK[tool.risk];
            return (
              <li key={tool.name} className="flex items-center gap-2 px-3 py-2">
                <span className="flex-1">{tool.label}</span>
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <risk.icon className="size-3.5" /> {risk.label}
                </span>
              </li>
            );
          })}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}
