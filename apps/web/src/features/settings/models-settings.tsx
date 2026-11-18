"use client";

import { useEffect } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { actions, useAuthStatus, useCurrentUser, useModelProviders } from "@/data/store";
import { AddKeyDialog } from "./add-key-dialog";
import { ModelList } from "./model-list";
import { MyKeys } from "./my-keys";
import { ProviderCard } from "./provider-card";
import { SettingsSection } from "./settings-shell";

/**
 * Settings → Models & keys. Owners and admins connect model providers with the org's API keys;
 * every member can add their own (My keys), which only their own requests use. Everyone sees which
 * are connected and the models they can use. Keys are checked live when saved.
 */
export function ModelsSettings() {
  const providers = useModelProviders();
  const canManage = useCurrentUser().role !== "member";

  const authStatus = useAuthStatus();

  // Model lists change; ask again when the page opens (the API answers from its cache if it can).
  useEffect(() => {
    if (authStatus === "signed-in") void actions.loadModels();
  }, [authStatus]);

  return (
    <div className="flex flex-col gap-8">
      <SettingsSection
        title="Providers"
        description={canManage
          ? "Add your organization's API key for a provider and its models become available to every bot. Keys are encrypted and never shown again."
          : "Owners and admins add the organization's API keys. Here's what's connected. You can add your own under My keys."}
        action={canManage && <AddKeyDialog trigger={<Button size="sm" variant="outline"><Plus /> Custom server</Button>} />}
      >
        <ul className="grid gap-3 @xl:grid-cols-2">
          {providers.map((p) => <ProviderCard key={p.id} provider={p} canManage={canManage} />)}
        </ul>
      </SettingsSection>

      <SettingsSection
        title="My keys"
        description="Your own API key for a provider. Only you see it, and only your requests use it (your messages, routines and triggers), before the organization's key. You pay that provider directly."
      >
        <MyKeys />
      </SettingsSection>

      <SettingsSection title="Models" description="What bots can pick from right now, straight from each provider. Prices are per million tokens, in and out.">
        <ModelList />
      </SettingsSection>
    </div>
  );
}
