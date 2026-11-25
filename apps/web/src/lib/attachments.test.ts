import { describe, expect, it } from "vitest";
import { chatPath, fileNameOf, freePath, hasThumbnail, pastedFileName, previewOf } from "./attachments";

describe("chatPath", () => {
  it("puts the file in the chat folder under its own name", () => {
    expect(chatPath("report.pdf")).toBe("chat/report.pdf");
  });

  it("swaps characters the API refuses, and drops trailing dots and spaces", () => {
    expect(chatPath('Q3: plan "final"?.md')).toBe("chat/Q3- plan -final--.md");
    expect(chatPath("notes. ")).toBe("chat/notes");
    expect(chatPath("..")).toBe("chat/file");
  });

  it("numbers a name already taken in this message, before its extension", () => {
    expect(chatPath("plan.md", ["chat/plan.md"])).toBe("chat/plan (2).md");
    expect(chatPath("plan.md", ["chat/plan.md", "chat/plan (2).md"])).toBe("chat/plan (3).md");
    expect(chatPath("README", ["chat/README"])).toBe("chat/README (2)");
    expect(chatPath(".env", ["chat/.env"])).toBe("chat/.env (2)");
  });
});

describe("pastedFileName", () => {
  const at = new Date(2026, 10, 25, 10, 30, 5);

  it("gives a pasted screenshot the time it was pasted", () => {
    expect(pastedFileName("image.png", at)).toBe("image-2026-11-25-103005.png");
    expect(pastedFileName("image.JPEG", at)).toBe("image-2026-11-25-103005.jpeg");
  });

  it("keeps the name of a file copied from a folder", () => {
    expect(pastedFileName("invoice.pdf", at)).toBe("invoice.pdf");
    expect(pastedFileName("image-1.png", at)).toBe("image-1.png");
  });
});

describe("fileNameOf", () => {
  it("drops the folders", () => {
    expect(fileNameOf("chat/report.pdf")).toBe("report.pdf");
    expect(fileNameOf("report.pdf")).toBe("report.pdf");
  });
});

describe("hasThumbnail", () => {
  it("is true for pictures the API shows, not SVG or other files", () => {
    expect(hasThumbnail("image/png")).toBe(true);
    expect(hasThumbnail("image/jpeg; charset=binary")).toBe(true);
    expect(hasThumbnail("image/svg+xml")).toBe(false);
    expect(hasThumbnail("application/pdf")).toBe(false);
  });
});

describe("freePath", () => {
  it("keeps a free path and numbers a taken one in its folder", () => {
    expect(freePath("chat/q3.pdf", [])).toBe("chat/q3.pdf");
    expect(freePath("chat/q3.pdf", ["chat/q3.pdf", "chat/q3 (2).pdf"])).toBe("chat/q3 (3).pdf");
    expect(freePath("notes", ["notes"])).toBe("notes (2)");
  });
});

describe("previewOf", () => {
  it("shows the text, else what was attached, as the API does", () => {
    const file = { type: "file", path: "chat/a.pdf" };
    expect(previewOf([{ type: "text", text: "Look" }, file])).toBe("Look");
    expect(previewOf([file])).toBe("Sent a.pdf");
    expect(previewOf([file, file, file])).toBe("Sent 3 files");
    expect(previewOf([])).toBe("");
  });
});
