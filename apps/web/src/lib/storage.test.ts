import { describe, expect, it } from "vitest";
import { describeBucket, draftFrom, draftProblems, presetFor } from "./storage";

describe("presetFor", () => {
  it("knows the common services by their endpoint, and AWS by having none", () => {
    expect(presetFor("").id).toBe("aws");
    expect(presetFor("https://abc123.r2.cloudflarestorage.com").id).toBe("r2");
    expect(presetFor("https://s3.us-west-004.backblazeb2.com").id).toBe("b2");
    expect(presetFor("https://t3.storage.dev").id).toBe("tigris");
    expect(presetFor("https://minio.acme.dev").id).toBe("other");
  });
});

describe("describeBucket", () => {
  it("names the host (or AWS), the bucket and its folder", () => {
    expect(describeBucket({ endpoint: "", bucket: "acme-files", prefix: "" })).toBe("AWS / acme-files");
    expect(describeBucket({ endpoint: "https://abc.r2.cloudflarestorage.com/", bucket: "acme", prefix: "team/botdesk" }))
      .toBe("abc.r2.cloudflarestorage.com / acme/team/botdesk");
  });
});

describe("draftProblems", () => {
  const filled = { ...draftFrom(), region: "auto", bucket: "acme", accessKeyId: "AKIA1234", secretAccessKey: "s3cret" };

  it("asks for everything a new bucket needs", () => {
    expect(Object.keys(draftProblems(draftFrom(), false)).sort()).toEqual(["accessKeyId", "bucket", "region", "secretAccessKey"]);
    expect(draftProblems(filled, false)).toEqual({});
  });

  it("wants an endpoint for anything but AWS, with the preset's as an example", () => {
    expect(draftProblems({ ...filled, preset: "tigris" }, false).endpoint).toBe("Tigris needs its endpoint, like https://t3.storage.dev.");
  });

  it("keeps the saved secret when the field is left empty", () => {
    expect(draftProblems({ ...filled, secretAccessKey: "" }, true)).toEqual({});
  });
});
