/**
 * Markdown as one line of plain text, for previews such as the chat list, where `**bold**`
 * or a code fence would show their marks. Keeps the words, drops the formatting.
 */
export function markdownToPlain(markdown: string): string {
  return markdown
    .replace(/^\s*(```|~~~).*$/gm, "") // code fence lines (the code inside stays)
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1") // images → their alt text
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // links → their text
    .replace(/`([^`]*)`/g, "$1") // inline code
    .replace(/(\*\*|__|~~)(.+?)\1/g, "$2") // bold, strikethrough
    .replace(/(^|[\s(])[*_](\S(?:.*?\S)?)[*_](?=[\s).,!?:;]|$)/g, "$1$2") // italic
    .replace(/^\s{0,3}(#{1,6}\s+|>\s?|[-*+]\s+(\[[ xX]\]\s+)?|\d+[.)]\s+)/gm, "") // headings, quotes, list marks
    .replace(/\s+/g, " ")
    .trim();
}
