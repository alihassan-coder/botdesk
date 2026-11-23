import { useEffect, useId } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { actions, useFileList } from "@/data/store";
import type { Bot } from "@/data/types";
import { FileRow } from "./file-row";
import { UploadFilesButton } from "./upload-files-button";

/** A bot's Files (its Computer tab): what's in its folder, with Upload and Delete. Loaded each time it opens. */
export function BotFiles({ bot }: { bot: Bot }) {
  const list = useFileList(bot.id);
  const titleId = useId();

  useEffect(() => {
    void actions.loadFiles(bot.id);
  }, [bot.id]);

  const items = list?.items ?? [];

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 id={titleId} className="text-sm font-medium">Files</h3>
          <p className="truncate font-mono text-xs text-muted-foreground">botdesk/{bot.handle}/</p>
        </div>
        <UploadFilesButton bot={bot} />
      </div>

      {!list || (list.status === "loading" && items.length === 0) ? (
        <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading files">
          <Skeleton className="h-13 rounded-xl" />
          <Skeleton className="h-13 rounded-xl" />
        </div>
      ) : list.status === "error" ? (
        <div role="alert" className="flex flex-col items-center gap-2 py-6 text-center text-sm text-destructive">
          {list.error}
          <Button size="sm" variant="outline" onClick={() => void actions.loadFiles(bot.id)}>Try again</Button>
        </div>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-pretty text-muted-foreground">
          No files yet. Upload one, or ask {bot.name} to save something.
        </p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label={`${bot.name}'s files`}>
          {items.map((file) => <FileRow key={file.id} bot={bot} file={file} />)}
        </ul>
      )}
    </section>
  );
}
