import { useState } from "react";

/**
 * Dropping files onto an element: `dragging` while files are held over it (so it can say "Drop to
 * attach"), and `onFiles` with what was dropped. Other things dragged over it (text, links) are left
 * to the browser, so dragging text into the box still works.
 */
export function useFileDrop(onFiles: (files: File[]) => void) {
  const [dragging, setDragging] = useState(false);
  const holdsFiles = (e: React.DragEvent) => e.dataTransfer.types.includes("Files");

  return {
    dragging,
    handlers: {
      onDragEnter(e: React.DragEvent) {
        if (!holdsFiles(e)) return;
        e.preventDefault();
        setDragging(true);
      },
      onDragOver(e: React.DragEvent) {
        if (!holdsFiles(e)) return;
        // Without this the browser opens the file instead of dropping it here.
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      },
      onDragLeave(e: React.DragEvent) {
        // Moving between children fires leave too; only leaving the element itself counts.
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      },
      onDrop(e: React.DragEvent) {
        if (!holdsFiles(e)) return;
        e.preventDefault();
        setDragging(false);
        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) onFiles(files);
      },
    },
  };
}
