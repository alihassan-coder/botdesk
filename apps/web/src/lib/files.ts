import type { Bot, BotFile } from "@/data/types";
import { formatBytes } from "./format";

/** Where a list of Files lives: one bot's folder, or the shared one every bot can read. */
export interface FileFolder {
  /** The store's key for its list (`useFileList`, `loadFiles`): the bot's id, or "" for the shared folder. */
  key: string;
  /** The bot whose folder it is; none for the shared folder. */
  botId?: string;
  /** "Shared", or the bot's name. */
  name: string;
  /** Where it is in storage: "botdesk/_shared/", "botdesk/scout/". */
  path: string;
  /** In a sentence: "the shared folder", "Scout's folder". */
  phrase: string;
  /** The name of its list: "Shared files", "Scout's files". */
  listName: string;
}

export const SHARED_FOLDER: FileFolder = {
  key: "",
  name: "Shared",
  path: "botdesk/_shared/",
  phrase: "the shared folder",
  listName: "Shared files",
};

export function botFolder(bot: Pick<Bot, "id" | "name" | "handle">): FileFolder {
  return {
    key: bot.id,
    botId: bot.id,
    name: bot.name,
    path: `botdesk/${bot.handle}/`,
    phrase: `${bot.name}'s folder`,
    listName: `${bot.name}'s files`,
  };
}

/** How full a folder is: "3 files · 24 KB", "1 file · 190 B", or "Empty". */
export function folderSummary(items: Pick<BotFile, "sizeBytes">[]): string {
  if (items.length === 0) return "Empty";
  const bytes = items.reduce((total, f) => total + f.sizeBytes, 0);
  return `${items.length} ${items.length === 1 ? "file" : "files"} · ${formatBytes(bytes)}`;
}

/**
 * Where the folder really is: its files say (the API names a bot's folder "<handle>-<id>" when the
 * handle once belonged to another bot), else where it would be.
 */
export function folderPathOf(folder: FileFolder, items: Pick<BotFile, "folder">[]): string {
  return items[0]?.folder ? `${items[0].folder}/` : folder.path;
}
