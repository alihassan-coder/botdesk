import { useRef } from "react";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { FileFolder } from "@/lib/files";
import type { FileUploads } from "./use-upload-files";

/** Upload: pick one or more files and they go into the folder (see `useUploadFiles`). */
export function UploadFilesButton({ folder, uploads }: { folder: FileFolder; uploads: FileUploads }) {
  const input = useRef<HTMLInputElement>(null);
  const { progress } = uploads;

  return (
    <>
      {/* The button below opens it; the input itself stays out of sight and out of the tab order. */}
      <input ref={input} type="file" multiple hidden aria-label={`Upload files to ${folder.name}`}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = ""; // so picking the same file again uploads it again
          if (files.length > 0) void uploads.upload(files);
        }} />
      <Button size="sm" variant="outline" disabled={progress !== null} onClick={() => input.current?.click()}>
        <Upload />
        {progress === null ? "Upload" : progress.of > 1 ? `Uploading ${progress.at} of ${progress.of}…` : "Uploading…"}
      </Button>
    </>
  );
}
