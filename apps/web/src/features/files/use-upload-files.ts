import { useRef, useState } from "react";
import { toast } from "sonner";
import { actions } from "@/data/store";
import type { FileFolder } from "@/lib/files";

export interface FileUploads {
  /** Which file of the batch is on its way, or null when nothing is uploading. */
  progress: { at: number; of: number } | null;
  upload: (files: File[]) => Promise<void>;
}

/**
 * Uploads into a folder: files go at their own names, one after another (a name that's already
 * there is replaced). Each refusal is its own toast with the reason. One batch at a time.
 */
export function useUploadFiles(folder: FileFolder): FileUploads {
  const [progress, setProgress] = useState<FileUploads["progress"]>(null);
  const busy = useRef(false);

  async function upload(files: File[]) {
    if (busy.current) return void toast("Still uploading. Add more once it's done.");
    busy.current = true;
    let uploaded = 0;
    for (const [i, file] of files.entries()) {
      setProgress({ at: i + 1, of: files.length });
      const result = await actions.uploadFile(folder.botId, file);
      if (result.ok) uploaded++;
      else toast.error(`${file.name}: ${result.error}`);
    }
    busy.current = false;
    setProgress(null);
    if (uploaded === 0) return;
    if (files.length === 1) toast.success(`Uploaded ${files[0].name}`);
    else toast.success(uploaded === files.length ? `Uploaded ${uploaded} files` : `Uploaded ${uploaded} of ${files.length} files`);
  }

  return { progress, upload };
}
