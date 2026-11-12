import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useThreads } from "@/data/store";
import type { Thread } from "@/data/types";
import { ThreadRow } from "./thread-row";

/**
 * All conversations, in three sections: Pinned, Bots (your DMs) and Groups.
 * Used by the sidebar and by the phone home screen.
 *
 * Rows highlight the open chat using the URL, which Next.js only knows at request
 * time, so the list sits in <Suspense>: the page prerenders with a skeleton and the
 * real list appears straight away in the browser.
 */
export function ThreadList({ query = "", onNavigate }: { query?: string; onNavigate?: () => void }) {
  return (
    <Suspense fallback={<ThreadListSkeleton />}>
      <ThreadSections query={query} onNavigate={onNavigate} />
    </Suspense>
  );
}

function ThreadSections({ query, onNavigate }: { query: string; onNavigate?: () => void }) {
  const threads = useThreads();
  const matches = threads.filter((t) => t.title.toLowerCase().includes(query.trim().toLowerCase()));

  if (matches.length === 0) {
    return <p className="px-3 py-6 text-center text-sm text-muted-foreground">No bots or groups match “{query}”.</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <Section title="Pinned" threads={matches.filter((t) => t.pinned)} onNavigate={onNavigate} />
      <Section title="Bots" threads={matches.filter((t) => !t.pinned && t.kind === "dm")} onNavigate={onNavigate} />
      <Section title="Groups" threads={matches.filter((t) => !t.pinned && t.kind === "group")} onNavigate={onNavigate} />
    </div>
  );
}

function Section({ title, threads, onNavigate }: { title: string; threads: Thread[]; onNavigate?: () => void }) {
  if (threads.length === 0) return null;
  return (
    <section aria-label={title}>
      <h2 className="px-2 pb-1 text-xs font-medium text-muted-foreground">{title}</h2>
      <ul className="flex flex-col gap-0.5">
        {threads.map((thread) => (
          <li key={thread.id}>
            <ThreadRow thread={thread} onNavigate={onNavigate} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function ThreadListSkeleton() {
  return (
    <div className="flex flex-col gap-1 px-2 pt-6" aria-hidden>
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="flex items-center gap-3 py-2">
          <Skeleton className="size-9 rounded-[10px]" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-2.5 w-40" />
          </div>
        </div>
      ))}
    </div>
  );
}
