"use client";

import { useState } from "react";
import { useBots } from "@/data/store";
import { PageHeader } from "@/features/shell/page-header";
import { SHARED_FOLDER, botFolder } from "@/lib/files";
import { FolderPanel } from "./folder-panel";
import { FolderPicker, type FolderChoice } from "./folder-picker";

/**
 * /files — the organization's Files by folder: Shared first (every bot can read it), then one
 * folder per bot. Pick a folder to see, upload, open and delete its files.
 * Like Settings, the layout follows the space the page has (container queries), not the screen.
 */
export function FilesScreen() {
  const bots = useBots();
  const [selected, setSelected] = useState(SHARED_FOLDER.key);
  const choices: FolderChoice[] = [{ folder: SHARED_FOLDER }, ...bots.map((bot) => ({ folder: botFolder(bot), bot }))];
  // A bot removed while its folder is open: back to Shared.
  const open = choices.find((c) => c.folder.key === selected)?.folder ?? SHARED_FOLDER;

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Files" />
      <div className="@container flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-5xl flex-col gap-6 p-4 @md:p-6 @3xl:flex-row @3xl:gap-10 @3xl:p-8">
          <FolderPicker choices={choices} selected={open.key} onSelect={setSelected} />
          {/* A fresh panel per folder, so an upload's progress stays with the folder it goes to. */}
          <FolderPanel key={open.key} folder={open} />
        </div>
      </div>
    </div>
  );
}
