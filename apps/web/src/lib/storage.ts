import type { S3Storage } from "@/data/types";

/**
 * Settings → Computers: S3-compatible services people often pick. To the API they are all one
 * provider ("s3"); a preset only changes the form's hints and the pricing link, never what you typed.
 */
export interface StoragePreset {
  id: "aws" | "r2" | "b2" | "tigris" | "other";
  name: string;
  /** What its endpoint looks like. Empty: AWS needs none. */
  endpoint: string;
  region: string;
  /** The provider's own pricing page (prices change, so BotDesk links instead of quoting). None for your own server. */
  pricingUrl?: string;
}

export const STORAGE_PRESETS: StoragePreset[] = [
  { id: "aws", name: "AWS S3", endpoint: "", region: "us-east-1", pricingUrl: "https://aws.amazon.com/s3/pricing/" },
  { id: "r2", name: "Cloudflare R2", endpoint: "https://<account-id>.r2.cloudflarestorage.com", region: "auto", pricingUrl: "https://developers.cloudflare.com/r2/pricing/" },
  { id: "b2", name: "Backblaze B2", endpoint: "https://s3.<region>.backblazeb2.com", region: "us-west-004", pricingUrl: "https://www.backblaze.com/cloud-storage/pricing" },
  { id: "tigris", name: "Tigris", endpoint: "https://t3.storage.dev", region: "auto", pricingUrl: "https://www.tigrisdata.com/pricing/" },
  { id: "other", name: "MinIO / other", endpoint: "https://minio.example.com", region: "us-east-1" },
];

const presetById = (id: StoragePreset["id"]) => STORAGE_PRESETS.find((p) => p.id === id)!;

/** The preset a saved endpoint looks like, so changing storage starts on the right one. */
export function presetFor(endpoint: string): StoragePreset {
  const host = hostOf(endpoint);
  if (!host) return presetById("aws");
  if (host.endsWith(".r2.cloudflarestorage.com")) return presetById("r2");
  if (host.endsWith(".backblazeb2.com")) return presetById("b2");
  if (host === "t3.storage.dev" || host.endsWith(".tigris.dev")) return presetById("tigris");
  return presetById("other");
}

function hostOf(endpoint: string): string {
  if (!endpoint.trim()) return "";
  try {
    return new URL(endpoint.trim()).host;
  } catch {
    return endpoint.trim();
  }
}

/** Where the files go, in one line: "AWS / acme-files/botdesk", "abc.r2.cloudflarestorage.com / acme-files". */
export function describeBucket({ endpoint, bucket, prefix }: Pick<S3Storage, "endpoint" | "bucket" | "prefix">): string {
  return `${hostOf(endpoint) || "AWS"} / ${[bucket, prefix].filter(Boolean).join("/")}`;
}

/** The S3 form as typed. The access key ID is never shown again, so it always has to be pasted. */
export interface S3Draft {
  preset: StoragePreset["id"];
  endpoint: string;
  region: string;
  bucket: string;
  prefix: string;
  accessKeyId: string;
  secretAccessKey: string;
}

/** A form to start from: what's saved (without its keys), or nothing. */
export function draftFrom(saved?: S3Storage): S3Draft {
  return {
    preset: presetFor(saved?.endpoint ?? "").id,
    endpoint: saved?.endpoint ?? "", region: saved?.region ?? "", bucket: saved?.bucket ?? "", prefix: saved?.prefix ?? "",
    accessKeyId: "", secretAccessKey: "",
  };
}

export type S3Problems = Partial<Record<Exclude<keyof S3Draft, "preset">, string>>;

/**
 * What's missing before the API is asked (it checks the rest with a live write). `hasSavedSecret`:
 * storage that is already S3 keeps its secret when the field is left empty.
 */
export function draftProblems(draft: S3Draft, hasSavedSecret: boolean): S3Problems {
  const preset = presetById(draft.preset);
  const problems: S3Problems = {};
  if (preset.id !== "aws" && !draft.endpoint.trim()) {
    problems.endpoint = preset.id === "other" ? "Add your server's endpoint." : `${preset.name} needs its endpoint, like ${preset.endpoint}.`;
  }
  if (!draft.region.trim()) problems.region = `Add the region, like ${preset.region}.`;
  if (draft.bucket.trim().length < 3) problems.bucket = "Add the bucket's name (at least 3 characters).";
  if (draft.accessKeyId.trim().length < 4) problems.accessKeyId = "Paste the access key ID.";
  if (!hasSavedSecret && !draft.secretAccessKey.trim()) problems.secretAccessKey = "Paste the secret access key.";
  return problems;
}
