import { useEffect, useId } from "react";
import { actions, useFileList } from "@/data/store";
import type { Bot } from "@/data/types";
import { botFolder } from "@/lib/files";
import { FolderFileList } from "./folder-file-list";
import { UploadFilesButton } from "./upload-files-button";
import { useUploadFiles } from "./use-upload-files";

/** A bot's Files (its Computer tab): what's in its folder, with Upload and Delete. Loaded each time it opens. */
export function BotFiles({ bot }: { bot: Bot }) {
  const folder = botFolder(bot);
  const list = useFileList(bot.id);
  const uploads = useUploadFiles(folder);
  const titleId = useId();

  useEffect(() => {
    void actions.loadFiles(bot.id);
  }, [bot.id]);

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 id={titleId} className="text-sm font-medium">Files</h3>
          <p className="truncate font-mono text-xs text-muted-foreground">{folder.path}</p>
        </div>
        <UploadFilesButton folder={folder} uploads={uploads} />
      </div>
      <FolderFileList
        folder={folder}
        list={list}
        empty={
          <p className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-pretty text-muted-foreground">
            No files yet. Upload one, or ask {bot.name} to save something.
          </p>
        }
      />
    </section>
  );
}
