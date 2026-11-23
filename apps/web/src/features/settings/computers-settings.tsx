"use client";

import { Globe } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { SettingsSection } from "./settings-shell";
import { StorageCard } from "./storage-card";

/**
 * Settings → Computers (ADR 0017): what bots use besides apps. Storage for their files now;
 * a browser comes next.
 */
export function ComputersSettings() {
  return (
    <div className="flex flex-col gap-8">
      <SettingsSection title="Storage" description="Where your bots keep files.">
        <StorageCard />
      </SettingsSection>

      <SettingsSection title="Browser" action={<Badge variant="secondary">Coming soon</Badge>}>
        <div className="flex items-start gap-3 rounded-2xl border border-dashed p-4 text-sm text-muted-foreground">
          <Globe className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p className="text-pretty">
            Bots get a web browser next, for websites with no integration. You&apos;ll watch it work and take over to sign in.
          </p>
        </div>
      </SettingsSection>
    </div>
  );
}
