"use client";

import { PageHeader } from "@/features/shell/page-header";
import { SettingsNav } from "./settings-nav";

/** The frame for every settings section: header, section links, then the section. */
export function SettingsShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Settings" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-5xl flex-col gap-6 p-4 md:flex-row md:gap-10 md:p-8">
          <SettingsNav />
          <div className="min-w-0 flex-1">{children}</div>
        </div>
      </div>
    </div>
  );
}

/** A titled block inside a settings section. */
export function SettingsSection({ title, description, children, action }: { title: string; description?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4 border-b pb-8 last:border-b-0" aria-label={title}>
      <div className="flex items-start gap-4">
        <div className="flex-1">
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
          {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
