import { useId } from "react";
import { Upload } from "lucide-react";
import { useFileList, useOrg } from "@/data/store";
import { useFileDrop } from "@/hooks/use-file-drop";
import { folderPathOf, folderSummary, type FileFolder } from "@/lib/files";
import { cn } from "@/lib/utils";
import { FolderFileList } from "./folder-file-list";
import { UploadFilesButton } from "./upload-files-button";
import { useUploadFiles } from "./use-upload-files";

/**
 * One folder on the Files page: what it's for, where it is, how full, and its files with Upload
 * and Delete. Files dropped anywhere on it upload into it.
 */
export function FolderPanel({ folder }: { folder: FileFolder }) {
  const list = useFileList(folder.key);
  const orgName = useOrg().name;
  const uploads = useUploadFiles(folder);
  const drop = useFileDrop((files) => void uploads.upload(files));
  const titleId = useId();
  const shared = !folder.botId;
  const ready = list?.status === "ready";

  return (
    <section aria-labelledby={titleId} className="relative flex min-w-0 flex-1 flex-col gap-4" {...drop.handlers}>
      <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
        <div className="min-w-[min(100%,16rem)] flex-1">
          <h2 id={titleId} className="text-lg font-semibold tracking-tight">{folder.name}</h2>
          <p className="mt-0.5 text-sm text-pretty text-muted-foreground">
            {shared ? `Every bot in ${orgName || "your organization"} can read these.` : `What ${folder.name} saves, and files you give it.`}
          </p>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            <span className="font-mono">{folderPathOf(folder, list?.items ?? [])}</span>
            {ready && <span className="tabular-nums"> · {folderSummary(list.items)}</span>}
          </p>
        </div>
        <UploadFilesButton folder={folder} uploads={uploads} />
      </div>

      <FolderFileList
        folder={folder}
        list={list}
        empty={
          <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed px-6 py-10 text-center">
            <Upload aria-hidden className="size-5 text-muted-foreground" />
            <p className="max-w-sm text-sm text-pretty">
              {shared ? "Files every bot can read. Upload a brand guide or price list here." : `No files yet. Upload one, or ask ${folder.name} to save something.`}
            </p>
            <p className="text-xs text-muted-foreground">You can also drop files here.</p>
          </div>
        }
      />

      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute -inset-2 grid place-items-center rounded-2xl border-2 border-dashed border-brand bg-background/90 text-sm font-medium text-brand transition-opacity duration-150 ease-out",
          drop.dragging ? "opacity-100" : "opacity-0",
        )}
      >
        Drop to upload to {folder.name}
      </div>
    </section>
  );
}
