import { CircleAlert, RotateCw, X } from "lucide-react";
import {
  Attachment, AttachmentAction, AttachmentActions, AttachmentContent, AttachmentDescription, AttachmentMedia, AttachmentTitle,
} from "@/components/ui/attachment";
import { Spinner } from "@/components/ui/spinner";
import { FileTypeIcon } from "@/features/files/file-type-icon";
import { fileNameOf, hasThumbnail } from "@/lib/attachments";
import { formatBytes } from "@/lib/format";
import type { DraftAttachment } from "./use-attachments";

/**
 * The files attached to the message being written, above the box. Each says whether it's uploading,
 * ready (its size) or refused (the API's reason, with Retry). Remove takes it off the message.
 */
export function AttachmentChips({
  drafts,
  onRemove,
  onRetry,
}: {
  drafts: DraftAttachment[];
  onRemove: (key: number) => void;
  onRetry: (key: number) => void;
}) {
  return (
    <ul aria-label="Attached files" className="flex flex-wrap gap-2 px-1.5 pt-1.5">
      {drafts.map((draft) => (
        <li key={draft.key} className="max-w-full">
          <AttachmentChip draft={draft} onRemove={() => onRemove(draft.key)} onRetry={() => onRetry(draft.key)} />
        </li>
      ))}
    </ul>
  );
}

function AttachmentChip({ draft, onRemove, onRetry }: { draft: DraftAttachment; onRemove: () => void; onRetry: () => void }) {
  const name = fileNameOf(draft.path);
  const failed = draft.status === "failed";
  const state = failed ? "error" : draft.status === "uploading" ? "uploading" : "done";
  const thumbnail = draft.saved?.url && hasThumbnail(draft.saved.contentType) ? draft.saved.url : "";

  return (
    <Attachment size="sm" state={state} className="max-w-72">
      <AttachmentMedia variant={thumbnail ? "image" : "icon"}>
        {draft.status === "uploading" ? (
          <Spinner aria-label={`Uploading ${name}`} />
        ) : failed ? (
          <CircleAlert aria-hidden />
        ) : thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element -- the API's bytes need the session cookie; next/image would fetch them without it
          <img src={thumbnail} alt="" width={32} height={32} />
        ) : (
          <FileTypeIcon type={draft.file.type} className="text-muted-foreground" />
        )}
      </AttachmentMedia>
      <AttachmentContent>
        <AttachmentTitle title={draft.path}>{name}</AttachmentTitle>
        <AttachmentDescription title={draft.error} className={failed ? "line-clamp-2 whitespace-normal" : undefined}>
          {failed ? draft.error : draft.status === "uploading" ? "Uploading…" : formatBytes(draft.file.size)}
        </AttachmentDescription>
      </AttachmentContent>
      <AttachmentActions>
        {failed && (
          <AttachmentAction aria-label={`Retry ${name}`} onClick={onRetry}>
            <RotateCw />
          </AttachmentAction>
        )}
        <AttachmentAction aria-label={`Remove ${name}`} onClick={onRemove}>
          <X />
        </AttachmentAction>
      </AttachmentActions>
    </Attachment>
  );
}
