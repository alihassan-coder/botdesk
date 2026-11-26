import { useEffect } from "react";
import { FolderOpen } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { actions, useAuthStatus, useFileList, useOrg } from "@/data/store";
import type { Bot } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { folderSummary, type FileFolder } from "@/lib/files";
import { cn } from "@/lib/utils";

export interface FolderChoice {
  folder: FileFolder;
  /** The bot whose folder it is, for its avatar; none for the shared folder. */
  bot?: Bot;
}

/**
 * The folders on the Files page, Shared first: a column beside the files on wider screens, a row
 * that scrolls sideways on narrow ones. Each loads its list, so it can say how full it is.
 */
export function FolderPicker({ choices, selected, onSelect }: { choices: FolderChoice[]; selected: string; onSelect: (key: string) => void }) {
  return (
    <ul
      aria-label="Folders"
      className="scroll-fade-x -mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none] @3xl:sticky @3xl:top-8 @3xl:mx-0 @3xl:w-60 @3xl:shrink-0 @3xl:flex-col @3xl:self-start @3xl:overflow-visible @3xl:px-0 @3xl:mask-none"
    >
      {choices.map(({ folder, bot }) => (
        <FolderButton key={folder.key} folder={folder} bot={bot} selected={folder.key === selected} onSelect={() => onSelect(folder.key)} />
      ))}
    </ul>
  );
}

function FolderButton({ folder, bot, selected, onSelect }: { folder: FileFolder; bot?: Bot; selected: boolean; onSelect: () => void }) {
  const list = useFileList(folder.key);
  const signedIn = useAuthStatus() === "signed-in";
  const orgId = useOrg().id;

  useEffect(() => {
    if (signedIn) void actions.loadFiles(folder.key);
  }, [signedIn, orgId, folder.key]);

  const loading = !list || (list.status === "loading" && list.items.length === 0);

  return (
    // Shared stands apart from the bots' folders under it.
    <li className={cn("shrink-0", !folder.botId && "@3xl:mb-2 @3xl:border-b @3xl:pb-2")}>
      <button
        type="button"
        aria-current={selected ? "true" : undefined}
        onClick={onSelect}
        className={cn(
          "flex w-44 items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50 @3xl:w-full",
          selected ? "bg-muted" : "hover:bg-muted/60",
        )}
      >
        {bot ? (
          <BotAvatar name={bot.name} color={bot.avatarColor} />
        ) : (
          <span aria-hidden className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-brand/10 text-brand">
            <FolderOpen className="size-4.5" />
          </span>
        )}
        <span className="min-w-0 flex-1">
          <span className={cn("block truncate text-sm", selected ? "font-semibold" : "font-medium")}>{folder.name}</span>
          {/* Keeps the name and the count apart when read out as one ("Shared 2 files · 4 KB"). */}{" "}
          {loading ? (
            <>
              <Skeleton aria-hidden className="mt-1 h-3 w-16 rounded-sm" />
              <span className="sr-only">Counting files…</span>
            </>
          ) : (
            <span className="block truncate text-xs text-muted-foreground tabular-nums">
              {list.status === "error" ? "Didn't load" : folderSummary(list.items)}
            </span>
          )}
        </span>
      </button>
    </li>
  );
}
