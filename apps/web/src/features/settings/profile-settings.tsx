"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions, useCurrentUser } from "@/data/store";
import { MemberAvatar } from "@/features/bots/bot-avatar";
import { SettingsSection } from "./settings-shell";

/** Settings → Profile: your name and @handle (how bots and teammates mention you). */
export function ProfileSettings() {
  const user = useCurrentUser();
  const [name, setName] = useState(user.name);
  const [handle, setHandle] = useState(user.handle);
  const changed = name !== user.name || handle !== user.handle;
  const valid = name.trim().length > 0 && /^[a-z0-9_-]+$/.test(handle);

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
          actions.updateCurrentUser({ name: name.trim(), handle });
          toast.success("Profile saved");
        }}
      >
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="profile-name">Name</FieldLabel>
            <Input id="profile-name" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field>
            <FieldLabel htmlFor="profile-handle">Handle</FieldLabel>
            <Input id="profile-handle" value={handle} onChange={(e) => setHandle(e.target.value.toLowerCase())} />
            <FieldDescription>Bots and teammates mention you as @{handle || "…"}. Letters, numbers, - and _.</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="profile-email">Email</FieldLabel>
            <Input id="profile-email" value={user.email} disabled />
          </Field>
          <Button type="submit" disabled={!changed || !valid} className="w-fit">
            Save changes
          </Button>
        </FieldGroup>
      </form>
    </SettingsSection>
  );
}
