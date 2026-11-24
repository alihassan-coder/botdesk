import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { FieldDescription, FieldLegend, FieldSet } from "@/components/ui/field";
import { RadioGroup } from "@/components/ui/radio-group";
import { actions } from "@/data/store";
import type { FileStorage, StorageProviderId } from "@/data/types";
import { CLOUDINARY, cloudinaryProblems, draftFrom, draftProblems, type CloudinaryDraft, type S3Draft } from "@/lib/storage";
import { CloudinaryFields } from "./cloudinary-fields";
import { ProviderOption } from "./provider-option";
import { S3Fields } from "./s3-fields";

/**
 * Change where the organization's files go (owners and admins). The API writes, reads and deletes
 * a small file before it switches, which can take a few seconds, so this says "Checking…" and then
 * either closes or shows the API's reason.
 */
export function StorageForm({ current, onDone }: { current: FileStorage; onDone: () => void }) {
  const [provider, setProvider] = useState<StorageProviderId>(current.localAvailable ? current.provider : "s3");
  const [draft, setDraft] = useState(() => draftFrom(current.s3));
  const [cloudinary, setCloudinary] = useState<CloudinaryDraft>(() => ({ cloudName: current.cloudinary?.cloudName ?? "", apiKey: "", apiSecret: "" }));
  const [tried, setTried] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const s3Missing = provider === "s3" ? draftProblems(draft, current.provider === "s3") : {};
  const cloudinaryMissing = provider === "cloudinary" ? cloudinaryProblems(cloudinary, current.provider === "cloudinary") : {};

  const edit = (next: S3Draft) => {
    setDraft(next);
    setError("");
  };
  const editCloudinary = (next: CloudinaryDraft) => {
    setCloudinary(next);
    setError("");
  };

  async function save() {
    setTried(true);
    if (Object.keys({ ...s3Missing, ...cloudinaryMissing }).length > 0) return;
    setChecking(true);
    setError("");
    const result = await actions.saveStorage(
      provider === "local" ? { provider } : provider === "cloudinary" ? { provider, cloudinary } : { provider, s3: draft },
    );
    setChecking(false);
    if (!result.ok) return setError(result.error);
    toast.success(provider === "local" ? "Files now go to this BotDesk server"
      : `Files now go to ${provider === "cloudinary" ? `Cloudinary (${cloudinary.cloudName.trim()})` : draft.bucket.trim()}`);
    onDone();
  }

  return (
    <form noValidate aria-label="Change storage" className="flex flex-col gap-6 rounded-2xl border p-4"
      onSubmit={(e) => { e.preventDefault(); if (!checking) void save(); }}>
      <FieldSet>
        <FieldLegend variant="label">Keep files</FieldLegend>
        <RadioGroup value={provider} onValueChange={(value) => { setProvider(value as StorageProviderId); setError(""); }}>
          <ProviderOption group="storage" value="local" label="Local" disabled={!current.localAvailable} autoFocus={provider === "local"}
            hint={current.localAvailable ? "On this BotDesk server. Lost if the server's disk is wiped." : "Turned off on this server."} />
          <ProviderOption group="storage" value="s3" label="S3-compatible" autoFocus={provider === "s3"}
            hint="Your own bucket: AWS S3, Cloudflare R2, Backblaze B2, Tigris, MinIO and others." />
          <ProviderOption group="storage" value="cloudinary" label="Cloudinary" autoFocus={provider === "cloudinary"} hint={CLOUDINARY.hint} />
        </RadioGroup>
        <FieldDescription>BotDesk is free; storage is billed by the provider you choose. Local is free.</FieldDescription>
      </FieldSet>

      {provider === "s3" && <S3Fields draft={draft} onChange={edit} problems={tried ? s3Missing : {}} saved={current.s3} />}
      {provider === "cloudinary" && (
        <CloudinaryFields draft={cloudinary} onChange={editCloudinary} problems={tried ? cloudinaryMissing : {}} saved={current.cloudinary} />
      )}

      {movesFiles(current, provider, draft, cloudinary) && (
        <p className="text-sm text-muted-foreground">
          Files saved so far stay where they are. Bots can open them again only if you switch back.
        </p>
      )}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" disabled={checking}>{checking ? "Checking…" : "Check and save"}</Button>
      </div>
    </form>
  );
}

/** Whether saving would send new files somewhere other than where the saved ones are. */
function movesFiles(current: FileStorage, provider: StorageProviderId, draft: S3Draft, cloudinary: CloudinaryDraft) {
  if (provider !== current.provider) return true;
  if (provider === "cloudinary") return cloudinary.cloudName.trim() !== current.cloudinary?.cloudName;
  if (provider === "local" || !current.s3) return false;
  const { endpoint, bucket, prefix } = current.s3;
  return draft.endpoint.trim().replace(/\/+$/, "") !== endpoint || draft.bucket.trim() !== bucket || draft.prefix.trim().replace(/^\/+|\/+$/g, "") !== prefix;
}
