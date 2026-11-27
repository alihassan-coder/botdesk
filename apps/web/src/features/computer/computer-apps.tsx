import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { CloudComputer } from "@/data/types";
import { isWorkspaceOnly } from "@/lib/computer";

/**
 * What runs on a bot's cloud computer: its apps (long-running processes, with their ports) and the
 * URLs made for its ports. A URL only the Orgo workspace's members can open says so.
 */
export function ComputerApps({ computer }: { computer: CloudComputer }) {
  const { apps, previews } = computer;
  if (apps.length === 0 && previews.length === 0) return null;

  return (
    <div className="flex flex-col gap-3">
      {apps.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <h4 className="text-xs font-medium text-muted-foreground">Apps</h4>
          <ul className="flex flex-col divide-y rounded-xl border">
            {apps.map((app) => (
              <li key={app.name} className="flex items-center gap-2 px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate font-mono text-xs">{app.name}</span>
                {app.port !== null && <span className="font-mono text-xs text-muted-foreground tabular-nums">:{app.port}</span>}
                <Badge variant={app.status === "running" ? "secondary" : app.status === "failed" || app.status === "crashing" ? "destructive" : "outline"}>
                  {app.status}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
      {previews.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <h4 className="text-xs font-medium text-muted-foreground">Previews</h4>
          <ul className="flex flex-col gap-1.5">
            {previews.map((preview) => (
              <li key={preview.url} className="text-sm">
                <a href={preview.url} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1 font-medium text-brand hover:underline">
                  <span className="truncate">{preview.url}</span>
                  <ExternalLink className="size-3.5 shrink-0" aria-hidden />
                </a>
                <span className="block text-xs text-pretty text-muted-foreground">
                  Port {preview.port}
                  {isWorkspaceOnly(preview.access) && " · only people in your Orgo workspace can open it"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
