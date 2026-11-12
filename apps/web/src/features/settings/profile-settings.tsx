"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions, useBots, useCurrentUser, useUsers } from "@/data/store";
import { MemberAvatar } from "@/features/bots/bot-avatar";
import { FormError } from "@/features/auth/form-error";
import { PasswordSettings } from "./password-settings";
import { SettingsSection } from "./settings-shell";

/** The API's rule for handles: a–z and 0–9, words joined by single dashes, 2 or more characters. */
const HANDLE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/** Settings → Profile: your name and @handle (how bots and teammates mention you), and your password. */
export function ProfileSettings() {
  return (
    <div className="flex flex-col gap-8">
      <ProfileForm />
      <PasswordSettings />
    </div>
  );
}

function ProfileForm() {
  const user = useCurrentUser();
  const [name, setName] = useState(user.name);
  const [handle, setHandle] = useState(user.handle);
  const [error, setError] = useState<string | null>(null);
  const [saving, startSaving] = useTransition();
  const handleTaken = useHandleTakenByOthers(handle, user.id);
  const changed = name.trim() !== user.name || handle !== user.handle;
  const valid = name.trim().length > 0 && handle.length >= 2 && HANDLE.test(handle) && !handleTaken;

  const save = () =>
    startSaving(async () => {
      setError(null);
      const result = await actions.updateCurrentUser({ name: name.trim(), handle });
      if (result.ok) toast.success("Profile saved");
      else setError(result.error);
    });

  return (
    <SettingsSection title="Profile" description="How you appear to your team and your bots.">
      <div className="flex items-center gap-4">
        <MemberAvatar name={name || user.name} size="lg" />
        <div>
          <p className="font-medium">{user.name}</p>
          <p className="text-sm text-muted-foreground capitalize">{user.role}</p>
        </div>
      </div>
      <form
        className="max-w-md"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <FieldGroup>
          {error && <FormError>{error}</FormError>}
          <Field>
            <FieldLabel htmlFor="profile-name">Name</FieldLabel>
            <Input id="profile-name" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field data-invalid={handleTaken}>
            <FieldLabel htmlFor="profile-handle">Handle</FieldLabel>
            <Input id="profile-handle" value={handle} onChange={(e) => setHandle(e.target.value.toLowerCase())} aria-invalid={handleTaken} />
            {handleTaken && <FieldError>@{handle} is already someone else&apos;s. Mentions need to reach one person or bot.</FieldError>}
            <FieldDescription>Bots and teammates mention you as @{handle || "…"}. Lowercase letters and numbers, with single dashes between words.</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="profile-email">Email</FieldLabel>
            <Input id="profile-email" value={user.email} disabled />
          </Field>
          <Button type="submit" disabled={!changed || !valid || saving} className="w-fit">
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </FieldGroup>
      </form>
    </SettingsSection>
  );
}

/** True when a teammate or a bot already answers to this @handle. */
function useHandleTakenByOthers(handle: string, myId: string) {
  const users = useUsers();
  const bots = useBots();
  return users.some((u) => u.id !== myId && u.handle === handle) || bots.some((b) => b.handle === handle);
}
