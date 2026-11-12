"use client";

import { useTheme } from "next-themes";
import { Check, Monitor, Moon, Pipette, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import { isHexColor, readableTextOn } from "@/lib/color";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ACCENTS, applyAccent, useAccent, type Accent } from "./accent";
import { SettingsSection } from "./settings-shell";

const THEMES = [
  { id: "light", label: "Light", icon: Sun, preview: "bg-white border-neutral-200", bar: "bg-neutral-200" },
  { id: "dark", label: "Dark", icon: Moon, preview: "bg-neutral-900 border-neutral-700", bar: "bg-neutral-700" },
  { id: "system", label: "System", icon: Monitor, preview: "bg-gradient-to-r from-white from-50% to-neutral-900 to-50% border-neutral-300", bar: "bg-neutral-400" },
];

/*
 * The radio itself is an invisible layer over the whole card or swatch: the card is what you
 * see, the radio is what you click, focus and arrow through. (`after:hidden` drops the
 * radio's enlarged hit area, which would spill onto the neighbouring card.)
 */
const COVER = "absolute inset-0 z-10 size-full cursor-pointer rounded-[inherit] border-0 opacity-0 after:hidden";

/**
 * Settings → Appearance: light/dark/system and the accent colour. Saved in this browser.
 * Both pickers are radio groups: one Tab stop each, arrow keys move and select.
 */
export function AppearanceSettings() {
  const { theme, setTheme } = useTheme();
  const [accent, setAccent] = useAccent();
  const pickAccent = (next: Accent) => {
    setAccent(next);
    applyAccent(next);
  };

  return (
    <div className="flex flex-col gap-8">
      <SettingsSection title="Theme" description="Follow your device, or pick one.">
        <RadioGroup value={theme ?? ""} onValueChange={setTheme} aria-label="Theme" className="grid grid-cols-3 gap-3 sm:max-w-lg">
          {THEMES.map((t) => (
            <div
              key={t.id}
              className={cn(
                "relative flex flex-col gap-2 rounded-2xl border p-2 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
                theme === t.id && "border-brand ring-2 ring-brand/20",
              )}
            >
              <RadioGroupItem value={t.id} aria-label={t.label} className={COVER} />
              <span className={cn("flex h-16 flex-col gap-1.5 rounded-xl border p-2", t.preview)}>
                <span className={cn("h-1.5 w-1/2 rounded-full", t.bar)} />
                <span className={cn("h-1.5 w-3/4 rounded-full", t.bar)} />
                <span className="mt-auto h-2 w-1/3 self-end rounded-full bg-brand" />
              </span>
              <span className="flex items-center gap-1.5 px-1 text-sm font-medium">
                <t.icon className="size-3.5" /> {t.label}
              </span>
            </div>
          ))}
        </RadioGroup>
      </SettingsSection>

      <SettingsSection title="Accent colour" description="Used for approvals, mentions and highlights.">
        {/* The custom colour sits outside the radio group: it is its own control (a colour input), so it gets its own Tab stop. */}
        <div className="flex flex-wrap gap-3">
          <RadioGroup value={isHexColor(accent) ? "" : accent} onValueChange={(id) => pickAccent(id as Accent)} aria-label="Accent colour" className="flex w-auto flex-wrap gap-3">
            {ACCENTS.map((a) => {
              const selected = accent === a.id;
              return (
                <div key={a.id} className="relative flex flex-col items-center gap-1.5 text-xs">
                  <RadioGroupItem value={a.id} aria-label={a.label} className={cn("peer", COVER)} />
                  <span
                    style={{ backgroundColor: a.light }}
                    className={cn(
                      "grid size-10 place-items-center rounded-full text-white ring-offset-2 ring-offset-background peer-focus-visible:ring-2 peer-focus-visible:ring-ring",
                      selected && "ring-2 ring-foreground",
                    )}
                  >
                    {selected && <Check className="size-4" />}
                  </span>
                  {a.label}
                </div>
              );
            })}
          </RadioGroup>
          <CustomAccent value={isHexColor(accent) ? accent : null} onChange={pickAccent} />
        </div>
      </SettingsSection>
    </div>
  );
}

/**
 * "Custom": any colour from the system colour picker. The swatch shows a rainbow until
 * a custom colour is chosen, then that colour and its hex code.
 */
function CustomAccent({ value, onChange }: { value: `#${string}` | null; onChange: (hex: `#${string}`) => void }) {
  return (
    <label className="flex cursor-pointer flex-col items-center gap-1.5 text-xs">
      <span
        style={value ? { backgroundColor: value } : { background: "conic-gradient(#ff3b30, #ffcc00, #34c759, #0a84ff, #bf5af2, #ff3b30)" }}
        className={cn(
          "relative grid size-10 place-items-center rounded-full ring-offset-2 ring-offset-background focus-within:ring-2 focus-within:ring-ring",
          value && "ring-2 ring-foreground",
        )}
      >
        {value ? <Check className="size-4" style={{ color: readableTextOn(value) }} /> : <Pipette className="size-4 text-white drop-shadow" />}
        <input
          type="color"
          aria-label={value ? `Custom colour, ${value} selected` : "Custom colour"}
          value={value ?? "#3b30ff"}
          onChange={(e) => onChange(e.target.value as `#${string}`)}
          className="absolute inset-0 cursor-pointer opacity-0"
        />
      </span>
      {value ? value.toUpperCase() : "Custom"}
    </label>
  );
}
