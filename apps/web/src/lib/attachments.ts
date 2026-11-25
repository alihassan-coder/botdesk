/*
 * Files attached in chat. They're uploaded first (into the DM's bot's folder, or the shared one in a
 * group) under `chat/`, then sent with the message by id. The rules here match the API's
 * (`file_service.clean_path`, `MAX_ATTACHMENTS`), so a name a person picked never fails on its path.
 */

/** The API takes at most this many files per message. */
export const MAX_ATTACHMENTS = 10;

/** The folder chat attachments go in, inside the bot's (or the shared) folder. */
export const CHAT_FOLDER = "chat";

/** Characters no part of a path may hold on the API (Windows refuses them). */
const BAD_CHARACTERS = /[\x00-\x1f<>:"|?*\\/]/g;

/**
 * Where an attached file is saved: `chat/<its name>`, made safe for the API's path rules, and kept
 * apart from the paths already taken in this message ("plan (2).md"), since saving a path again
 * replaces that file.
 */
export function chatPath(name: string, taken: Iterable<string> = []): string {
  const safe = name.replace(BAD_CHARACTERS, "-").trim().replace(/[.\s]+$/, "") || "file";
  const used = new Set(taken);
  const dot = safe.lastIndexOf(".");
  const [stem, extension] = dot > 0 ? [safe.slice(0, dot), safe.slice(dot)] : [safe, ""];
  let path = `${CHAT_FOLDER}/${safe}`;
  for (let n = 2; used.has(path); n++) path = `${CHAT_FOLDER}/${stem} (${n})${extension}`;
  return path;
}

/**
 * A pasted picture's name. Browsers call every pasted screenshot "image.png", so the second one
 * would replace the first: it gets the time it was pasted instead ("image-2026-11-25-103005.png").
 * Files copied from a folder keep their own names.
 */
export function pastedFileName(name: string, at: Date): string {
  const match = /^image(\.\w+)$/i.exec(name);
  if (!match) return name;
  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp = `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}-${pad(at.getHours())}${pad(at.getMinutes())}${pad(at.getSeconds())}`;
  return `image-${stamp}${match[1].toLowerCase()}`;
}

/** The file's own name, without its folders: "chat/report.pdf" → "report.pdf". */
export function fileNameOf(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

/** Pictures the API shows in the browser, so they can be a thumbnail (never SVG: see the API's `_INLINE`). */
const THUMBNAIL_TYPES = new Set(["image/png", "image/jpeg", "image/gif", "image/webp", "image/avif"]);

export function hasThumbnail(contentType: string): boolean {
  return THUMBNAIL_TYPES.has(contentType.split(";")[0].trim().toLowerCase());
}
