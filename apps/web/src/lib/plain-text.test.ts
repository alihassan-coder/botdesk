import { describe, expect, it } from "vitest";
import { markdownToPlain } from "./plain-text";

describe("markdownToPlain", () => {
  it("drops bold, italic, strikethrough and inline code marks", () => {
    expect(markdownToPlain("**Done**: sent _two_ emails with ~~one~~ `send_email`")).toBe("Done: sent two emails with one send_email");
  });

  it("keeps link and image text, not the URL", () => {
    expect(markdownToPlain("See [the doc](https://x.dev/a) and ![chart](https://x.dev/c.png)")).toBe("See the doc and chart");
  });

  it("drops headings, quotes, list and task marks, and joins lines", () => {
    expect(markdownToPlain("## Plan\n> note\n- one\n2. two\n- [x] three")).toBe("Plan note one two three");
  });

  it("keeps the code inside a fence", () => {
    expect(markdownToPlain("Run:\n```bash\npnpm test\n```")).toBe("Run: pnpm test");
  });

  it("leaves snake_case names and plain text alone", () => {
    expect(markdownToPlain("call send_email to sara@acme.dev")).toBe("call send_email to sara@acme.dev");
  });
});
