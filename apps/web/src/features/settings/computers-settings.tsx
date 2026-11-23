"use client";

import { Globe } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { SettingsSection } from "./settings-shell";
import { StorageCard } from "./storage-card";

/**
 * Settings → Computers (ADR 0017): what bots use besides apps. Storage for their files, and
 * their browsers (Local for now; choosing a cloud browser comes later).
 */
export function ComputersSettings() {
  return (
    <div className="flex flex-col gap-8">
      <SettingsSection title="Storage" description="Where your bots keep files.">
        <StorageCard />
      </SettingsSection>

      <SettingsSection title="Browser" description="For websites with no integration.">
        <div className="flex items-start gap-3 rounded-2xl border p-4">
          <span className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-muted text-muted-foreground">
            <Globe className="size-4.5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-center gap-2 font-medium">Local <Badge variant="secondary">Cloud browsers coming soon</Badge></p>
            <p className="text-sm text-pretty text-muted-foreground">
              Each bot has its own browser on this BotDesk server. Watch it and take over in the bot&apos;s Computer tab.
            </p>
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
