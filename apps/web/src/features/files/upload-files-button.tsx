import { useRef, useState } from "react";
import { toast } from "sonner";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";
import type { Bot } from "@/data/types";

/**
 * Upload: pick one or more files and they go into the bot's folder at their own names, one after
 * another (a name that's already there is replaced). Each refusal is its own toast with the reason.
 */
export function UploadFilesButton({ bot }: { bot: Bot }) {
  const input = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<{ at: number; of: number } | null>(null);

  async function upload(files: File[]) {
    let uploaded = 0;
    for (const [i, file] of files.entries()) {
      setProgress({ at: i + 1, of: files.length });
      const result = await actions.uploadFile(bot.id, file);
      if (result.ok) uploaded++;
      else toast.error(`${file.name}: ${result.error}`);
    }
    setProgress(null);
    if (uploaded === 0) return;
    if (files.length === 1) toast.success(`Uploaded ${files[0].name}`);
    else toast.success(uploaded === files.length ? `Uploaded ${uploaded} files` : `Uploaded ${uploaded} of ${files.length} files`);
  }

  return (
    <>
      {/* The button below opens it; the input itself stays out of sight and out of the tab order. */}
      <input ref={input} type="file" multiple hidden aria-label={`Upload files to ${bot.name}`}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = ""; // so picking the same file again uploads it again
          if (files.length > 0) void upload(files);
        }} />
      <Button size="sm" variant="outline" disabled={progress !== null} onClick={() => input.current?.click()}>
        <Upload />
        {progress === null ? "Upload" : progress.of > 1 ? `Uploading ${progress.at} of ${progress.of}…` : "Uploading…"}
      </Button>
    </>
  );
}
