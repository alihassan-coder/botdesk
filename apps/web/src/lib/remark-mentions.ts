import { splitMentions } from "./mentions";

/** The few fields of a markdown (mdast) node this plugin reads and writes. */
export interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
  data?: { hName?: string; hProperties?: Record<string, unknown>; hChildren?: { type: "text"; value: string }[] };
}

// Code and links keep their text as written: an @ in a code sample or a URL isn't a mention.
const SKIP = new Set(["inlineCode", "code", "link", "linkReference"]);

/**
 * A remark plugin for react-markdown: wraps each @handle in plain text in a span with the
 * brand colour, the same way plain messages show them.
 */
export function remarkMentions() {
  return (tree: MdNode) => colourMentions(tree);
}

function colourMentions(node: MdNode): void {
  if (!node.children || SKIP.has(node.type)) return;
  node.children = node.children.flatMap((child) => {
    if (child.type !== "text" || !child.value) {
      colourMentions(child);
      return [child];
    }
    const pieces = splitMentions(child.value);
    if (!pieces.some((piece) => piece.isMention)) return [child];
    return pieces.map((piece) => (piece.isMention ? mentionNode(piece.text) : { type: "text", value: piece.text }));
  });
}

function mentionNode(handle: string): MdNode {
  return {
    type: "mention",
    data: { hName: "span", hProperties: { className: ["font-medium", "text-brand"] }, hChildren: [{ type: "text", value: handle }] },
  };
}
