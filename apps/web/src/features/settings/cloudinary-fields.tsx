import { FieldGroup } from "@/components/ui/field";
import type { CloudinaryStorage } from "@/data/types";
import { CLOUDINARY, type CloudinaryDraft, type CloudinaryProblems } from "@/lib/storage";
import { SecretField } from "./secret-field";
import { TextField } from "./text-field";

interface CloudinaryFieldsProps {
  draft: CloudinaryDraft;
  onChange: (draft: CloudinaryDraft) => void;
  /** Shown once a save was tried. */
  problems: CloudinaryProblems;
  /** What's saved now, if storage is already Cloudinary: its secret is kept when the field is left empty. */
  saved?: CloudinaryStorage;
}

/** Cloudinary's details: the cloud name, API key and API secret from its dashboard. */
export function CloudinaryFields({ draft, onChange, problems, saved }: CloudinaryFieldsProps) {
  const change = (key: keyof CloudinaryDraft) => (value: string) => onChange({ ...draft, [key]: value });

  return (
    <FieldGroup>
      <a href={CLOUDINARY.pricingUrl} target="_blank" rel="noreferrer" className="w-fit text-sm underline underline-offset-4 hover:text-primary">
        Cloudinary pricing
      </a>
      <div className="grid gap-x-4 gap-y-7 @lg:grid-cols-2">
        <TextField id="cloudinary-name" label="Cloud name" value={draft.cloudName} onChange={change("cloudName")} problem={problems.cloudName} placeholder="acme" />
        <TextField id="cloudinary-key" label="API key" value={draft.apiKey} onChange={change("apiKey")} problem={problems.apiKey}
          hint={saved ? `Paste it again to save changes. The saved one ends in ${saved.apiKeyHint}.` : undefined} />
      </div>
      <SecretField id="cloudinary-secret" label="API secret" value={draft.apiSecret} onChange={change("apiSecret")} problem={problems.apiSecret}
        keepsSaved={saved !== undefined} />
    </FieldGroup>
  );
}
