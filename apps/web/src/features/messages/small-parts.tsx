import Link from "next/link";
import { Repeat } from "lucide-react";
import type { RoutineCreatedPart as RoutineCreatedPartData } from "@/data/types";

/*
 * The one-line parts. Each is a few lines long, so they share a file;
 * if one grows, give it its own file like the bigger cards (a file's card is `file-part.tsx`).
 */

/** "Created a routine: Overnight outbound". */
export function RoutineCreatedPart({ part }: { part: RoutineCreatedPartData }) {
  return (
    <Link href="/routines" className="flex w-fit items-center gap-2 rounded-full border px-3 py-1 text-xs text-muted-foreground hover:text-foreground">
      <Repeat className="size-3.5 text-brand" />
      Created a routine: <span className="font-medium text-foreground">{part.name}</span>
    </Link>
  );
}
