"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { pluralize } from "@/lib/format";
import { finishSlug, slugWhileTyping } from "@/lib/handle";
import { actions, useBots, useOrg, useUsers } from "@/data/store";
import { OrgAvatar } from "@/features/shell/org-avatar";
import { SettingsSection } from "./settings-shell";

/** Settings → Organization: the org's name and address, what's in it, and deleting it. */
export function OrganizationSettings() {
  const org = useOrg();
  const users = useUsers();
  const bots = useBots();
  const [name, setName] = useState(org.name);
  const [slug, setSlug] = useState(org.slug);
  const [saving, startSaving] = useTransition();
  const finalSlug = finishSlug(slug);
  const changed = name.trim() !== org.name || finalSlug !== org.slug;
  const valid = name.trim().length > 0 && finalSlug.length > 0;

  return (
    <div className="flex flex-col gap-8">
      <SettingsSection title="Organization" description="Everything your team shares: bots, chats, apps, keys and budgets.">
        <div className="flex items-center gap-4">
          <OrgAvatar name={name || org.name} className="size-14 rounded-2xl text-xl" />
          <div>
            <p className="font-medium">{org.name}</p>
            <p className="text-sm text-muted-foreground">
              {pluralize(users.length, "person", "people")} · {pluralize(bots.length, "bot")}
            </p>
          </div>
        </div>
        <form
          className="max-w-md"
          onSubmit={(e) => {
            e.preventDefault();
            startSaving(async () => {
              // Send only what changed, so an unchanged address is never re-checked.
              const patch = { ...(name.trim() !== org.name && { name: name.trim() }), ...(finalSlug !== org.slug && { slug: finalSlug }) };
              const result = await actions.updateOrg(patch);
              if (!result.ok) return void toast.error(result.error);
              setSlug(finalSlug);
              toast.success("Organization saved");
            });
          }}
        >
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="org-name">Name</FieldLabel>
              <Input id="org-name" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="org-slug">Address</FieldLabel>
              <Input id="org-slug" value={slug} onChange={(e) => setSlug(slugWhileTyping(e.target.value))} />
              <FieldDescription>botdesk.app/{finalSlug || "…"}. Lowercase letters, numbers and dashes.</FieldDescription>
            </Field>
            <Button type="submit" disabled={!changed || !valid || saving} className="w-fit">{saving ? "Saving…" : "Save changes"}</Button>
          </FieldGroup>
        </form>
      </SettingsSection>

      <SettingsSection title="People" description="Invite teammates and set what they can do.">
        <Button asChild variant="outline" className="w-fit">
          <Link href="/settings/members">Manage members</Link>
        </Button>
      </SettingsSection>

      <SettingsSection title="Delete organization" description="Removes every bot, chat, routine, connection and key. This can't be undone.">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive" className="w-fit">Delete {org.name}</Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete {org.name}?</AlertDialogTitle>
              <AlertDialogDescription>
                Every bot stops, and every chat, routine, connection and key is deleted for {pluralize(users.length, "person", "people")}. This can&apos;t be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep it</AlertDialogCancel>
              <AlertDialogAction variant="destructive" onClick={() => toast("Deleting an organization arrives with the API. Nothing was deleted.")}>Delete</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </SettingsSection>
    </div>
  );
}
