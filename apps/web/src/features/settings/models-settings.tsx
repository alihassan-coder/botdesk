"use client";

import { KeyRound, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TimeAgo } from "@/components/time-ago";
import { formatCount } from "@/lib/format";
import { actions, useCredentials, useModels } from "@/data/store";
import { AddKeyDialog } from "./add-key-dialog";
import { SettingsSection } from "./settings-shell";

/** Settings → Models & keys: which models bots can use, and whose API key pays. */
export function ModelsSettings() {
  const models = useModels();
  const credentials = useCredentials();

  return (
    <div className="flex flex-col gap-8">
      <SettingsSection title="Models" description="Every bot picks one of these. Prices are per million tokens, in and out.">
        <ul className="flex flex-col divide-y rounded-2xl border">
          {models.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 p-4">
              <div className="min-w-40 flex-1">
                <p className="font-medium">{m.name}</p>
                <p className="text-sm text-muted-foreground">{m.provider}</p>
              </div>
              <div className="flex flex-wrap gap-1">
                {m.capabilities.map((c) => (
                  <span key={c} className="rounded-full bg-muted px-2 py-0.5 text-xs capitalize">{c.replace("-", " ")}</span>
                ))}
              </div>
              <p className="w-36 text-right text-sm text-muted-foreground tabular-nums">
                {m.priceInPerMTok === 0 ? "Free (local)" : `$${m.priceInPerMTok} / $${m.priceOutPerMTok}`}
                <span className="block text-xs">{formatCount(m.contextWindow)} context</span>
              </p>
            </li>
          ))}
        </ul>
      </SettingsSection>

      <SettingsSection
        title="API keys"
        description="A bot uses the first key that applies: its own override, then a key the org enforces, then yours, then the org default."
        action={<AddKeyDialog />}
      >
        <ul className="flex flex-col gap-2">
          {credentials.map((k) => (
            <li key={k.id} className="flex items-center gap-3 rounded-2xl border p-4">
              <span className="grid size-9 place-items-center rounded-xl bg-muted"><KeyRound className="size-4 text-muted-foreground" /></span>
              <div className="min-w-0 flex-1">
                <p className="font-medium">
                  {k.provider} <span className="font-normal text-muted-foreground">· {k.label}</span>
                </p>
                <p className="truncate font-mono text-xs text-muted-foreground">
                  {k.baseUrl ?? k.maskedKey}
                  {k.lastUsedAt && <> · used <TimeAgo iso={k.lastUsedAt} /></>}
                </p>
              </div>
              <span className="hidden rounded-full bg-muted px-2 py-0.5 text-xs sm:inline">{k.owner === "org" ? "Org" : "Personal"}</span>
              <Button variant="ghost" size="icon-sm" onClick={() => actions.removeCredential(k.id)} aria-label={`Remove ${k.provider} ${k.label}`}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      </SettingsSection>
    </div>
  );
}
