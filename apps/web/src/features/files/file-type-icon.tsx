import { File as FileIcon, FileArchive, FileAudio, FileImage, FileSpreadsheet, FileText, FileVideo } from "lucide-react";

/** A file's icon from its type: image, video, audio, spreadsheet, text, archive, or a plain file. Used in Files and in chat. */
export function FileTypeIcon({ type, className }: { type: string; className?: string }) {
  const props = { className, "aria-hidden": true } as const;
  if (type.startsWith("image/")) return <FileImage {...props} />;
  if (type.startsWith("video/")) return <FileVideo {...props} />;
  if (type.startsWith("audio/")) return <FileAudio {...props} />;
  if (type === "text/csv" || type.includes("spreadsheet") || type.includes("excel")) return <FileSpreadsheet {...props} />;
  if (type.startsWith("text/") || type === "application/json" || type === "application/pdf") return <FileText {...props} />;
  if (/zip|compressed|tar|gzip/.test(type)) return <FileArchive {...props} />;
  return <FileIcon {...props} />;
}
