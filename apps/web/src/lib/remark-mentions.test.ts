import { describe, expect, it } from "vitest";
import { remarkMentions, type MdNode } from "./remark-mentions";

const paragraph = (...children: MdNode[]): MdNode => ({ type: "root", children: [{ type: "paragraph", children }] });
const run = (tree: MdNode): MdNode[] => {
  remarkMentions()(tree);
  return tree.children?.[0].children ?? [];
};

describe("remarkMentions", () => {
  it("wraps an @handle in a brand-coloured span", () => {
    const [before, mention, after] = run(paragraph({ type: "text", value: "ask @inbox now" }));
    expect(before).toEqual({ type: "text", value: "ask " });
    expect(mention).toMatchObject({ type: "mention", data: { hName: "span", hChildren: [{ type: "text", value: "@inbox" }] } });
    expect(after).toEqual({ type: "text", value: " now" });
  });

  it("leaves email addresses, inline code and links as they are", () => {
    const code = { type: "inlineCode", value: "@inbox" };
    const link = { type: "link", children: [{ type: "text", value: "@inbox" }] };
    const text = { type: "text", value: "to=sara@acme.dev" };
    expect(run(paragraph(text, code, link))).toEqual([text, code, link]);
  });

  it("finds handles inside bold text", () => {
    const [strong] = run(paragraph({ type: "strong", children: [{ type: "text", value: "@sara" }] }));
    expect(strong.children?.[0].type).toBe("mention");
  });
});
