"use client";

import { PageHeader } from "./page-header";
import { BotdeskMark } from "./logo";

/** Placeholder for pages planned in a later slice (see docs/frontend/README.md → Build order). */
export function ComingSoon({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex h-full flex-col">
      <PageHeader title={title} />
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
        <BotdeskMark className="size-10 text-muted-foreground/40" />
        <h2 className="text-lg font-semibold tracking-tight">{title} is on its way</h2>
        <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}
