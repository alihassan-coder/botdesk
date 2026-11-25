import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { FilePart as FilePartData } from "@/data/types";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { FilePart } from "./file-part";

const report: FilePartData = { type: "file", fileId: "f1", botId: "b1", path: "chat/q3-report.pdf", contentType: "application/pdf", sizeBytes: 1_468_006 };
const photo: FilePartData = { type: "file", fileId: "f2", path: "chat/whiteboard.png", contentType: "image/png", sizeBytes: 52_000 };

describe("FilePart on the API", () => {
  withFakeApi();

  it("shows the file's name and size, and opens its content in a new tab", async () => {
    await signInOnApi();
    renderUI(<FilePart part={report} />);
    const link = screen.getByRole("link", { name: "q3-report.pdf" });
    expect(link).toHaveAttribute("href", "http://api.test/api/v1/orgs/o1/files/f1/content");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByText("1.4 MB")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows a thumbnail of a picture", async () => {
    await signInOnApi();
    renderUI(<FilePart part={photo} />);
    expect(screen.getByRole("img", { name: "whiteboard.png" })).toHaveAttribute("src", "http://api.test/api/v1/orgs/o1/files/f2/content");
    expect(screen.getByRole("link", { name: "whiteboard.png" })).toBeInTheDocument();
    expect(screen.getByText("51 KB")).toBeInTheDocument();
  });
});

describe("FilePart in the demo", () => {
  it("names a file it can't open without linking it", () => {
    // jsdom makes no blob: URLs, so a demo file has nothing to open here.
    renderUI(<FilePart part={report} />);
    expect(screen.getByText("q3-report.pdf")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
