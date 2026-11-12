"use client";

import { useNow } from "@/hooks/use-now";
import { formatClockTime, formatShortAgo } from "@/lib/format";

/*
 * Times depend on the viewer's clock and timezone, which the server doesn't know.
 * Both components render nothing on the server and fill in right after the page
 * loads (see useNow), so server and browser HTML always match.
 */

/** "5m", "3h", "Yesterday"… */
export function TimeAgo({ iso, className }: { iso: string; className?: string }) {
  const now = useNow();
  return (
    <time dateTime={iso} className={className}>
      {now === null ? "" : formatShortAgo(iso, now)}
    </time>
  );
}

/** "9:41 AM", in the viewer's timezone. */
export function ClockTime({ iso, className }: { iso: string; className?: string }) {
  const now = useNow();
  return (
    <time dateTime={iso} className={className}>
      {now === null ? "" : formatClockTime(iso)}
    </time>
  );
}
