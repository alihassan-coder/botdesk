import { Repeat } from "lucide-react";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";

export const ROUTINES_COMING_SOON = "Bots can't run on a schedule yet. Routines arrive with the scheduler.";

/**
 * On the API there's no scheduler yet, so nothing would ever run a routine. Routines screens say
 * that plainly instead of saving one that never runs. `children`: what to offer instead.
 */
export function RoutinesComingSoon({ children }: { children?: React.ReactNode }) {
  return (
    <Empty className="border border-dashed">
      <EmptyHeader>
        <EmptyMedia variant="icon"><Repeat /></EmptyMedia>
        <EmptyTitle>Routines are coming soon</EmptyTitle>
        <EmptyDescription>{ROUTINES_COMING_SOON}</EmptyDescription>
      </EmptyHeader>
      {children && <EmptyContent>{children}</EmptyContent>}
    </Empty>
  );
}
