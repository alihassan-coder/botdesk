import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { FilesScreen } from "./files-screen";

const folderNames = () =>
  within(screen.getByRole("list", { name: "Folders" })).getAllByRole("button").map((b) => b.querySelector(".truncate")?.textContent);

describe("FilesScreen in the demo", () => {
  beforeEach(async () => {
    await actions.signIn("ali@acme.dev", "botdesk123");
  });

  it("lists Shared first, then one folder per bot, each with how full it is", async () => {
    renderUI(<FilesScreen />);
    expect(folderNames()).toEqual(["Shared", "Chief", "Inbox Manager", "Sales Outbound", "Talent Scout", "Expense Manager", "Bug Fixer"]);
    expect(await screen.findByRole("button", { name: /^Inbox Manager 3 files · / })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Talent Scout 1 file · / })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Shared Empty" })).toHaveAttribute("aria-current", "true");
  });

  it("opens on Shared, which says what goes there", () => {
    renderUI(<FilesScreen />);
    const shared = screen.getByRole("region", { name: "Shared" });
    expect(within(shared).getByText("Every bot in Acme Labs can read these.")).toBeInTheDocument();
    expect(within(shared).getByText("botdesk/_shared/")).toBeInTheDocument();
    expect(within(shared).getByText("Files every bot can read. Upload a brand guide or price list here.")).toBeInTheDocument();
  });

  it("picking a bot's folder shows its files", async () => {
    const { user } = renderUI(<FilesScreen />);
    await user.click(await screen.findByRole("button", { name: /^Inbox Manager/ }));
    const panel = screen.getByRole("region", { name: "Inbox Manager" });
    expect(within(panel).getByText("botdesk/inbox/")).toBeInTheDocument();
    expect(within(within(panel).getByRole("list", { name: "Inbox Manager's files" })).getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByRole("button", { name: /^Inbox Manager/ })).toHaveAttribute("aria-current", "true");
  });

  it("uploads into Shared, for every bot", async () => {
    const { user } = renderUI(<FilesScreen />);
    await user.upload(screen.getByLabelText("Upload files to Shared"), new File(["# Brand"], "brand-guide.md", { type: "text/markdown" }));

    const list = await screen.findByRole("list", { name: "Shared files" });
    expect(within(list).getByTitle("brand-guide.md")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Shared 1 file · 7 B" })).toBeInTheDocument();
    expect(getStoreSnapshot().fileLists[""].items[0]).toMatchObject({ path: "brand-guide.md", folder: "botdesk/_shared" });
    expect(getStoreSnapshot().fileLists[""].items[0].botId).toBeUndefined();
  });
});

describe("FilesScreen on the API", () => {
  const api = withFakeApi();
  const apiFile = (id: string, path: string, botId?: string) => ({
    id, ...(botId ? { botId } : {}), path, folder: botId ? "botdesk/scout" : "botdesk/_shared", contentType: "text/markdown",
    sizeBytes: 2048, available: true, createdAt: "2026-11-23T08:00:00", updatedAt: "2026-11-23T08:00:00",
  });

  it("loads the shared folder and each bot's, and uploads to Shared without a bot", async () => {
    api.routes["GET /api/v1/orgs/o1/files"] = { status: 200, body: [apiFile("f1", "price-list.md")] };
    api.routes["GET /api/v1/orgs/o1/files?botId=b1"] = { status: 200, body: [apiFile("f2", "notes.md", "b1"), apiFile("f3", "leads.md", "b1")] };
    api.routes["POST /api/v1/orgs/o1/files"] = { status: 201, body: apiFile("f4", "brand.md") };
    await signInOnApi();
    const { user } = renderUI(<FilesScreen />);

    expect(await screen.findByRole("button", { name: "Shared 1 file · 2 KB" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Scout 2 files · 4 KB" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "price-list.md" })).toHaveAttribute("href", "http://api.test/api/v1/orgs/o1/files/f1/content");

    await user.upload(screen.getByLabelText("Upload files to Shared"), new File(["# Brand"], "brand.md", { type: "text/markdown" }));
    expect(await screen.findByRole("link", { name: "brand.md" })).toBeInTheDocument();
    const upload = api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/files");
    expect(upload?.body).not.toHaveProperty("botId");
  });
});
