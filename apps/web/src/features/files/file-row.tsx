import { TimeAgo } from "@/components/time-ago";
import type { BotFile } from "@/data/types";
import type { FileFolder } from "@/lib/files";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";
import { DeleteFileButton } from "./delete-file-button";
import { FileTypeIcon } from "./file-type-icon";

/**
 * One file in a folder: its path (opens in a new tab), size and when it last changed.
 * One saved to storage the organization no longer uses is dimmed and can't be opened.
 */
export function FileRow({ folder, file }: { folder: FileFolder; file: BotFile }) {
  const slash = file.path.lastIndexOf("/") + 1;
  const name = (
    <>
      {slash > 0 && <span className="text-muted-foreground">{file.path.slice(0, slash)}</span>}
      {file.path.slice(slash)}
    </>
  );

  return (
    <li className={cn("flex items-center gap-3 rounded-xl border py-2 pr-1.5 pl-3", !file.available && "bg-muted/40")}>
      <FileTypeIcon type={file.contentType} className={cn("size-4 shrink-0 text-muted-foreground", !file.available && "opacity-60")} />
      <div className={cn("min-w-0 flex-1", !file.available && "opacity-60")}>
        {file.available && file.url ? (
          <a href={file.url} target="_blank" rel="noreferrer" title={file.path}
            className="block truncate rounded-sm text-sm font-medium hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
            {name}
          </a>
        ) : (
          <p className="truncate text-sm font-medium" title={file.path}>{name}</p>
        )}
        <p className="text-xs text-muted-foreground">
          {file.available ? <>{formatBytes(file.sizeBytes)} · <TimeAgo iso={file.updatedAt} /></> : "In storage you no longer use"}
        </p>
      </div>
      <DeleteFileButton folder={folder} file={file} />
    </li>
  );
}
