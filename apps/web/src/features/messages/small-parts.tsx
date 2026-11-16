import Link from "next/link";
import { FileText, Repeat } from "lucide-react";
import { formatBytes } from "@/lib/format";
import type { FilePart as FilePartData, RoutineCreatedPart as RoutineCreatedPartData } from "@/data/types";

/*
 * The two one-line parts. Each is a few lines long, so they share a file;
 * if one grows, give it its own file like the bigger cards.
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

/** A file the bot produced or shared. */
export function FilePart({ part }: { part: FilePartData }) {
  return (
    <div className="flex w-fit max-w-full items-center gap-3 rounded-xl border bg-card px-3 py-2">
      <FileText className="size-5 shrink-0 text-muted-foreground" />
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium">{part.name}</span>
        <span className="block text-xs text-muted-foreground">{formatBytes(part.sizeBytes)}</span>
      </span>
    </div>
  );
}
