import { useState } from "react";
import { Attachment, AttachmentContent, AttachmentDescription, AttachmentMedia, AttachmentTitle, AttachmentTrigger } from "@/components/ui/attachment";
import { useFileUrl } from "@/data/store";
import type { FilePart as FilePartData } from "@/data/types";
import { FileTypeIcon } from "@/features/files/file-type-icon";
import { fileNameOf, hasThumbnail } from "@/lib/attachments";
import { formatBytes } from "@/lib/format";

/**
 * A file in a message, the same whether a person attached it or a bot shared it, in a DM or a group:
 * its name and size, a thumbnail for pictures, and the whole card opens the file in a new tab.
 */
export function FilePart({ part }: { part: FilePartData }) {
  const url = useFileUrl(part);
  const name = fileNameOf(part.path);
  // A picture that doesn't load (deleted since, or signed out) falls back to its icon.
  const [broken, setBroken] = useState(false);
  const thumbnail = url && !broken && hasThumbnail(part.contentType);

  return (
    <Attachment className="max-w-xs has-[a:focus-visible]:ring-3 has-[a:focus-visible]:ring-ring/50" title={part.path}>
      <AttachmentMedia variant={thumbnail ? "image" : "icon"}>
        {thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element -- the API's bytes need the session cookie; next/image would fetch them without it
          <img src={url} alt={name} width={40} height={40} loading="lazy" decoding="async" onError={() => setBroken(true)} />
        ) : (
          <FileTypeIcon type={part.contentType} className="text-muted-foreground" />
        )}
      </AttachmentMedia>
      <AttachmentContent>
        <AttachmentTitle>{name}</AttachmentTitle>
        <AttachmentDescription>{formatBytes(part.sizeBytes)}</AttachmentDescription>
      </AttachmentContent>
      {url && (
        <AttachmentTrigger asChild>
          <a href={url} target="_blank" rel="noreferrer" aria-label={name} />
        </AttachmentTrigger>
      )}
    </Attachment>
  );
}
