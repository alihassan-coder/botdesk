import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { actions } from "@/data/store";
import type { BotFileList } from "@/data/types";
import type { FileFolder } from "@/lib/files";
import { FileRow } from "./file-row";

/**
 * A folder's files as last loaded: placeholders while the first list is on its way, the reason
 * with Try again when it fails, `empty` when there's nothing, else one row per file.
 */
export function FolderFileList({ folder, list, empty }: { folder: FileFolder; list?: BotFileList; empty: React.ReactNode }) {
  const items = list?.items ?? [];

  if (!list || (list.status === "loading" && items.length === 0)) {
    return (
      <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading files">
        <Skeleton className="h-13 rounded-xl" />
        <Skeleton className="h-13 rounded-xl" />
      </div>
    );
  }

  if (list.status === "error") {
    return (
      <div role="alert" className="flex flex-col items-center gap-2 py-6 text-center text-sm text-destructive">
        {list.error}
        <Button size="sm" variant="outline" onClick={() => void actions.loadFiles(folder.key)}>Try again</Button>
      </div>
    );
  }

  if (items.length === 0) return empty;

  return (
    <ul className="flex flex-col gap-2" aria-label={folder.listName}>
      {items.map((file) => <FileRow key={file.id} folder={folder} file={file} />)}
    </ul>
  );
}
