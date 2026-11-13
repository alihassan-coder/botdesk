import { useState } from "react";
import Link from "next/link";
import { ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useModelProviders, useModels } from "@/data/store";
import { formatContextWindow, groupModels } from "@/lib/models";

const ORG_DEFAULT = "Organization default";

/**
 * Pick a bot's model from the live lists of the org's connected providers: searchable, grouped by
 * provider. "" means the organization's default model. With nothing connected, it points to
 * Settings → Models & keys instead. A model that's gone from the lists still shows by its id.
 */
export function ModelPicker({ id, value, onChange }: { id: string; value: string; onChange: (modelId: string) => void }) {
  const [open, setOpen] = useState(false);
  const models = useModels();
  const providers = useModelProviders();
  const groups = groupModels(models, providers);
  const selected = models.find((m) => m.id === value);

  if (models.length === 0 && !providers.some((p) => p.connected)) {
    return (
      <p id={id} className="rounded-xl border border-dashed px-3 py-2 text-sm text-muted-foreground">
        No model provider is connected yet, so this bot will use the organization default.{" "}
        <Link href="/settings/models" className="font-medium text-foreground underline underline-offset-4">Add a key in Models &amp; keys</Link>
      </p>
    );
  }

  const pick = (modelId: string) => {
    onChange(modelId);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button id={id} type="button" variant="outline" role="combobox" aria-expanded={open} className="w-full justify-between font-normal">
          <span className="truncate">{selected?.name ?? (value || ORG_DEFAULT)}</span>
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) min-w-72 p-0" align="start">
        <Command>
          <CommandInput placeholder="Search models" />
          <CommandList>
            <CommandEmpty>No models match that.</CommandEmpty>
            <CommandGroup>
              <CommandItem value={ORG_DEFAULT} data-checked={value === ""} onSelect={() => pick("")}>{ORG_DEFAULT}</CommandItem>
            </CommandGroup>
            {groups.map((group) => (
              <CommandGroup key={group.providerId} heading={group.providerName}>
                {group.models.map((m) => (
                  <CommandItem key={m.id} value={`${m.name} ${m.id} ${group.providerName}`} data-checked={m.id === value} onSelect={() => pick(m.id)}>
                    {/* One flexible box, so the context window sits at the right edge, next to the tick. */}
                    <span className="flex min-w-0 flex-1 items-baseline justify-between gap-2">
                      <span className="truncate">{m.name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">{formatContextWindow(m)}</span>
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
