"use client";

import { useState } from "react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { actions, useBots } from "@/data/store";
import type { PolicyDecision, RiskClass, SecurityLevel } from "@/data/types";
import { RISK } from "@/features/approvals/risk";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { POLICY, SECURITY_LEVELS } from "@/features/bots/security-levels";
import { SecurityLevelPicker } from "@/features/bots/security-level-picker";
import { SettingsSection } from "./settings-shell";

const DECISION: Record<PolicyDecision, { label: string; className: string }> = {
  auto: { label: "Runs", className: "bg-success/12 text-success" },
  ask: { label: "Asks you", className: "bg-brand/12 text-brand" },
  deny: { label: "Blocked", className: "bg-muted text-muted-foreground" },
};

async function changeLevel(botId: string, securityLevel: SecurityLevel) {
  const result = await actions.editBot(botId, { securityLevel });
  if (!result.ok) toast.error(result.error);
}

/** Settings → Security: the org default, each bot's level, and exactly what every level allows. */
export function SecuritySettings() {
  const bots = useBots();
  const [orgDefault, setOrgDefault] = useState<SecurityLevel>("ask-before-acting");

  return (
    <div className="flex flex-col gap-8">
      <SettingsSection title="Default for new bots" description="New bots start here. When org, bot and routine settings differ, the strictest wins.">
        <SecurityLevelPicker
          value={orgDefault}
          onChange={(level) => {
            setOrgDefault(level);
            toast.success("Default security level saved");
          }}
        />
      </SettingsSection>

      <SettingsSection title="Your bots" description="Change how much each bot may do on its own.">
        <ul className="flex flex-col divide-y rounded-2xl border">
          {bots.map((bot) => (
            <li key={bot.id} className="flex items-center gap-3 p-3">
              <BotAvatar name={bot.name} color={bot.avatarColor} size="sm" />
              <span className="min-w-0 flex-1 truncate text-sm font-medium">{bot.name}</span>
              <Select value={bot.securityLevel} onValueChange={(v) => changeLevel(bot.id, v as SecurityLevel)}>
                <SelectTrigger className="w-40 sm:w-56" aria-label={`Security level for ${bot.name}`}><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SECURITY_LEVELS.map((l) => <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </li>
          ))}
        </ul>
      </SettingsSection>

      <SettingsSection title="What each level allows" description="Every action an app offers has a risk. The bot's level decides what happens.">
        <div className="overflow-x-auto rounded-2xl border">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b bg-muted/40 text-left">
                <th className="p-3 font-medium">Action</th>
                {SECURITY_LEVELS.map((l) => <th key={l.value} className="p-3 font-medium">{l.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {(Object.keys(RISK) as RiskClass[]).map((risk) => {
                const { label, icon: Icon } = RISK[risk];
                return (
                  <tr key={risk} className="border-b last:border-b-0">
                    <th scope="row" className="p-3 text-left font-normal">
                      <span className="flex items-center gap-2"><Icon className="size-4 text-muted-foreground" /> {label}</span>
                    </th>
                    {SECURITY_LEVELS.map((l) => {
                      const decision = DECISION[POLICY[l.value][risk]];
                      return (
                        <td key={l.value} className="p-3">
                          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", decision.className)}>{decision.label}</span>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </SettingsSection>
    </div>
  );
}
