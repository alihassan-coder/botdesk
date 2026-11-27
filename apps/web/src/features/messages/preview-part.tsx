import { ExternalLink, Globe } from "lucide-react";
import { isWorkspaceOnly } from "@/lib/computer";

/**
 * A URL the bot made for a port on its cloud computer (`computer.preview`), as a link card. A URL only
 * the Orgo workspace's members can open says so: anyone else gets Orgo's sign-in.
 */
export function PreviewPart({ preview }: { preview: { url: string; port?: number; access?: string } }) {
  return (
    <div className="flex w-full max-w-[560px] items-start gap-3 rounded-xl border px-3 py-2.5">
      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground" aria-hidden>
        <Globe className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-muted-foreground">{preview.port ? `Preview of port ${preview.port}` : "Preview"}</p>
        <a href={preview.url} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1 text-sm font-medium text-brand hover:underline">
          <span className="truncate">{preview.url}</span>
          <ExternalLink className="size-3.5 shrink-0" aria-hidden />
        </a>
        {isWorkspaceOnly(preview.access) && (
          <p className="text-xs text-pretty text-muted-foreground">Only people in your Orgo workspace can open it.</p>
        )}
      </div>
    </div>
  );
}
