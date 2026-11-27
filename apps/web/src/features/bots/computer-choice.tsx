import { useEffect, useId } from "react";
import Link from "next/link";
import { Globe, Monitor } from "lucide-react";
import { Field, FieldContent, FieldDescription, FieldLabel, FieldTitle } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { actions, useAuthStatus, useComputerProvider, useOrg } from "@/data/store";
import type { BotComputer } from "@/data/types";

interface ComputerChoiceProps {
  value: BotComputer;
  /** What the bot has now: switching away from it says what happens. */
  saved: BotComputer;
  onChange: (computer: BotComputer) => void;
}

/**
 * What a bot works on besides apps (ADR 0020): Files and a browser (the default), or Files and its own
 * cloud computer. The cloud computer needs the organization's Orgo key, so without one it stays visible
 * but unavailable, with where to add the key.
 */
export function ComputerChoice({ value, saved, onChange }: ComputerChoiceProps) {
  const load = useComputerProvider();
  const authStatus = useAuthStatus();
  const orgId = useOrg().id;
  const hintId = useId();
  const hasProvider = load.current?.provider !== undefined;

  useEffect(() => {
    if (authStatus === "signed-in") void actions.loadComputerProvider();
  }, [authStatus, orgId]);

  return (
    <div className="flex flex-col gap-2">
      <RadioGroup value={value} onValueChange={(v) => onChange(v as BotComputer)} aria-label="Computer" className="gap-2">
        <Option value="browser" icon={Globe} title="Files and a browser" description="Keeps files and browses websites that have no app." />
        <Option value="cloud" icon={Monitor} title="Files and a cloud computer" disabled={!hasProvider} describedBy={hasProvider ? undefined : hintId}
          description="Its own Linux computer: runs commands, tests and apps, with a screen you can watch. Orgo bills your organization while it runs." />
      </RadioGroup>
      {!hasProvider && (
        <FieldDescription id={hintId} className="text-xs">
          {load.status === "loading" ? "Checking for an Orgo key…" : (
            <>A cloud computer needs an Orgo key. An owner or admin adds one in{" "}
              <Link href="/settings/computers" className="font-medium text-brand hover:underline">Settings → Computers</Link>.</>
          )}
        </FieldDescription>
      )}
      {saved === "cloud" && value === "browser" && (
        <FieldDescription className="text-xs">Its cloud computer stops. Its disk is kept until you delete the computer in the Computer tab.</FieldDescription>
      )}
      {saved === "browser" && value === "cloud" && (
        <FieldDescription className="text-xs">It loses its browser tools: the cloud computer has a browser of its own.</FieldDescription>
      )}
    </div>
  );
}

interface OptionProps {
  value: BotComputer;
  icon: typeof Globe;
  title: string;
  description: string;
  disabled?: boolean;
  describedBy?: string;
}

function Option({ value, icon: Icon, title, description, disabled, describedBy }: OptionProps) {
  const id = `computer-${value}`;
  return (
    <FieldLabel htmlFor={id}>
      <Field orientation="horizontal" data-disabled={disabled || undefined}>
        <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <FieldContent>
          <FieldTitle>{title}</FieldTitle>
          <FieldDescription>{description}</FieldDescription>
        </FieldContent>
        <RadioGroupItem value={value} id={id} disabled={disabled} aria-describedby={describedBy} />
      </Field>
    </FieldLabel>
  );
}
