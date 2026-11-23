"use client";

import { BrowserProviderCard } from "./browser-provider-card";
import { SettingsSection } from "./settings-shell";
import { StorageCard } from "./storage-card";

/**
 * Settings → Computers (ADR 0017): what bots use besides apps. Where their files are kept, and
 * where their browsers run.
 */
export function ComputersSettings() {
  return (
    <div className="flex flex-col gap-8">
      <SettingsSection title="Storage" description="Where your bots keep files.">
        <StorageCard />
      </SettingsSection>

      <SettingsSection title="Browser" description="Where your bots' browsers run, for websites with no integration.">
        <BrowserProviderCard />
      </SettingsSection>
    </div>
  );
}
