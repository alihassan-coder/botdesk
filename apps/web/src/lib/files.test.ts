import { describe, expect, it } from "vitest";
import { SHARED_FOLDER, botFolder, folderSummary } from "./files";

describe("folders", () => {
  it("the shared folder is the store's empty key and has no bot", () => {
    expect(SHARED_FOLDER).toMatchObject({ key: "", name: "Shared", path: "botdesk/_shared/" });
    expect(SHARED_FOLDER.botId).toBeUndefined();
  });

  it("a bot's folder is named after its handle", () => {
    expect(botFolder({ id: "b1", name: "Scout", handle: "scout" })).toEqual({
      key: "b1", botId: "b1", name: "Scout", path: "botdesk/scout/", phrase: "Scout's folder", listName: "Scout's files",
    });
  });
});

describe("folderSummary", () => {
  it("counts the files and adds up their sizes", () => {
    expect(folderSummary([{ sizeBytes: 20_000 }, { sizeBytes: 4_576 }])).toBe("2 files · 24 KB");
    expect(folderSummary([{ sizeBytes: 190 }])).toBe("1 file · 190 B");
  });

  it("says when there's nothing in it", () => {
    expect(folderSummary([])).toBe("Empty");
  });
});
