import { FieldDescription, FieldGroup, FieldLegend, FieldSet } from "@/components/ui/field";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { S3Storage } from "@/data/types";
import { STORAGE_PRESETS, type S3Draft, type S3Problems } from "@/lib/storage";
import { SecretField } from "./secret-field";
import { TextField } from "./text-field";

interface S3FieldsProps {
  draft: S3Draft;
  onChange: (draft: S3Draft) => void;
  /** Shown once a save was tried. */
  problems: S3Problems;
  /** The bucket saved now, if storage is already S3: its secret is kept when the field is left empty. */
  saved?: S3Storage;
}

/** The bucket's details. Picking a service changes the hints and the pricing link, never what's typed. */
export function S3Fields({ draft, onChange, problems, saved }: S3FieldsProps) {
  const preset = STORAGE_PRESETS.find((p) => p.id === draft.preset) ?? STORAGE_PRESETS[0];
  const field = (key: keyof S3Problems) => ({
    value: draft[key],
    problem: problems[key],
    onChange: (value: string) => onChange({ ...draft, [key]: value }),
  });

  return (
    <FieldGroup>
      <FieldSet>
        <FieldLegend variant="label">Service</FieldLegend>
        <ToggleGroup type="single" variant="outline" size="sm" className="flex-wrap" aria-label="Service" value={draft.preset}
          onValueChange={(value) => value && onChange({ ...draft, preset: value as S3Draft["preset"] })}>
          {STORAGE_PRESETS.map((p) => <ToggleGroupItem key={p.id} value={p.id}>{p.name}</ToggleGroupItem>)}
        </ToggleGroup>
        <FieldDescription>
          {preset.pricingUrl
            ? <a href={preset.pricingUrl} target="_blank" rel="noreferrer">{preset.name} pricing</a>
            : "Any other S3-compatible service, or your own server. Check what it charges."}
        </FieldDescription>
      </FieldSet>

      <TextField id="storage-endpoint" label="Endpoint" {...field("endpoint")} inputMode="url"
        placeholder={preset.endpoint || "Leave empty for AWS"}
        hint={preset.id === "aws" ? "Leave empty for AWS itself." : "The bucket's address, starting with https://."} />
      <div className="grid gap-x-4 gap-y-7 @lg:grid-cols-2">
        <TextField id="storage-region" label="Region" {...field("region")} placeholder={preset.region} />
        <TextField id="storage-bucket" label="Bucket" {...field("bucket")} placeholder="acme-botdesk" />
      </div>
      <TextField id="storage-prefix" label="Folder prefix (optional)" {...field("prefix")} placeholder="team/files"
        hint="A folder inside the bucket to keep botdesk/ in. Leave empty for the bucket's top." />
      <div className="grid gap-x-4 gap-y-7 @lg:grid-cols-2">
        <TextField id="storage-key-id" label="Access key ID" {...field("accessKeyId")}
          hint={saved ? `Paste it again to save changes. The saved one ends in ${saved.accessKeyHint}.` : undefined} />
        <SecretField id="storage-secret" label="Secret access key" {...field("secretAccessKey")} keepsSaved={saved !== undefined} />
      </div>
    </FieldGroup>
  );
}
