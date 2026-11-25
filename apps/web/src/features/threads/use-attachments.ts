import { useRef, useState } from "react";
import { toast } from "sonner";
import { actions } from "@/data/store";
import type { BotFile, Thread } from "@/data/types";
import { MAX_ATTACHMENTS, chatPath, fileNameOf, pastedFileName } from "@/lib/attachments";

/** A file picked for the message being written: on its way up, uploaded (the saved file), or refused (the API's reason). */
export interface DraftAttachment {
  key: number;
  file: File;
  /** Where it's saved: "chat/report.pdf". */
  path: string;
  status: "uploading" | "uploaded" | "failed";
  saved?: BotFile;
  error?: string;
}

/**
 * The files attached to the message being written. Each uploads as soon as it's picked: in a DM into
 * the bot's folder, in a group into the shared one (only those can be attached there), under `chat/`.
 * `announcement` is for a live region, so screen readers hear when one is ready or refused.
 */
export function useAttachments(thread: Thread) {
  const botId = thread.kind === "dm" ? thread.botId : undefined;
  const [drafts, setDrafts] = useState<DraftAttachment[]>([]);
  const [announcement, setAnnouncement] = useState("");
  // Uploads finish later: the ref is the list as it is now, so a late answer never brings back a removed chip.
  const current = useRef<DraftAttachment[]>([]);
  const nextKey = useRef(0);

  function change(update: (list: DraftAttachment[]) => DraftAttachment[]) {
    current.current = update(current.current);
    setDrafts(current.current);
  }

  async function upload(draft: DraftAttachment) {
    const result = await actions.uploadFile(botId, draft.file, draft.path);
    if (!current.current.some((d) => d.key === draft.key)) return;
    change((list) => list.map((d) => (d.key !== draft.key ? d : result.ok
      ? { ...d, status: "uploaded", saved: result.file, error: undefined }
      : { ...d, status: "failed", error: result.error })));
    const name = fileNameOf(draft.path);
    setAnnouncement(result.ok ? `${name} attached.` : `${name} didn't upload. ${result.error}`);
  }

  /** Attach files (picked, dropped or pasted), up to the API's 10 per message. */
  function add(files: File[], { pasted = false } = {}) {
    const room = MAX_ATTACHMENTS - current.current.length;
    if (files.length > room) toast.error(`A message can have up to ${MAX_ATTACHMENTS} files.`);
    const taken = current.current.map((d) => d.path);
    const added = files.slice(0, Math.max(room, 0)).map((file): DraftAttachment => {
      const path = chatPath(pasted ? pastedFileName(file.name, new Date()) : file.name, taken);
      taken.push(path);
      return { key: nextKey.current++, file, path, status: "uploading" };
    });
    change((list) => [...list, ...added]);
    for (const draft of added) void upload(draft);
  }

  function retry(key: number) {
    const draft = current.current.find((d) => d.key === key);
    if (!draft) return;
    const again = { ...draft, status: "uploading" as const, error: undefined };
    change((list) => list.map((d) => (d.key === key ? again : d)));
    void upload(again);
  }

  /** Takes it off this message. A file that already uploaded stays in Files. */
  function remove(key: number) {
    change((list) => list.filter((d) => d.key !== key));
  }

  function clear() {
    change(() => []);
  }

  return {
    drafts,
    announcement,
    /** What the message would carry if sent now. */
    uploaded: drafts.flatMap((d) => (d.saved && d.status === "uploaded" ? [d.saved] : [])),
    isUploading: drafts.some((d) => d.status === "uploading"),
    add,
    retry,
    remove,
    clear,
    announce: setAnnouncement,
  };
}
