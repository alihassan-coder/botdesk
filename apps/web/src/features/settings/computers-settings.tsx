"use client";

import { BrowserProviderCard } from "./browser-provider-card";
import { CloudComputerCard } from "./cloud-computer-card";
import { SettingsSection } from "./settings-shell";
import { StorageCard } from "./storage-card";

/**
 * Settings → Computers (ADR 0017, 0020): what bots use besides apps. Where their files are kept,
 * where their browsers run, and the key for bots' own cloud computers.
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

      <SettingsSection title="Cloud computer" description="A computer of its own for each bot that needs to run things.">
        <CloudComputerCard />
      </SettingsSection>
    </div>
  );
}
