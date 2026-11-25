import { useRef } from "react";
import { Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";

/** The composer's paperclip: pick one or more files to attach to the message. */
export function AttachFilesButton({ onFiles }: { onFiles: (files: File[]) => void }) {
  const picker = useRef<HTMLInputElement>(null);
  return (
    <>
      <Button type="button" variant="ghost" size="icon" className="shrink-0 rounded-full" aria-label="Attach files" onClick={() => picker.current?.click()}>
        <Paperclip />
      </Button>
      {/* The paperclip opens it; the input itself stays out of sight and out of the tab order. */}
      <input ref={picker} type="file" multiple hidden aria-label="Choose files to attach"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = ""; // so picking the same file again attaches it again
          if (files.length > 0) onFiles(files);
        }} />
    </>
  );
}
