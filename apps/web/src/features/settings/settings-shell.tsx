"use client";

import { PageHeader } from "@/features/shell/page-header";
import { SettingsNav } from "./settings-nav";

/**
 * The frame for every settings section: header, section links, then the section.
 * Layouts follow the space settings has, not the screen (container queries): beside the app
 * sidebar on a tablet there's only ~540px, so the section links go on top as on a phone.
 * The section itself is a container too, so its cards and rows size to the column they're in.
 */
export function SettingsShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Settings" />
      <div className="@container flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-5xl flex-col gap-6 p-4 @md:p-6 @3xl:flex-row @3xl:gap-10 @3xl:p-8">
          <SettingsNav />
          <div className="@container min-w-0 flex-1">{children}</div>
        </div>
      </div>
    </div>
  );
}

/** A titled block inside a settings section. */
export function SettingsSection({ title, description, children, action }: { title: string; description?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4 border-b pb-8 last:border-b-0" aria-label={title}>
      <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
        <div className="min-w-[min(100%,16rem)] flex-1">
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
          {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
