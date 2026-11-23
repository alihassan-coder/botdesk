import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { BotFiles } from "./bot-files";

const botNamed = (name: string) => getStoreSnapshot().bots.find((b) => b.name === name)!;

describe("BotFiles in the demo", () => {
  it("lists the bot's files, with ones in storage the org no longer uses dimmed and not openable", () => {
    renderUI(<BotFiles bot={botNamed("Inbox Manager")} />);
    const list = screen.getByRole("list", { name: "Inbox Manager's files" });
    expect(within(list).getAllByRole("listitem").map((li) => li.querySelector("[title]")?.getAttribute("title"))).toEqual([
      "drafts/reply-to-sara.txt", "exports/october-senders.csv", "reports/inbox-this-week.md",
    ]);
    const old = within(list).getByText("In storage you no longer use").closest("li")!;
    expect(within(old).queryByRole("link")).not.toBeInTheDocument();
  });

  it("says how to get files when there are none", () => {
    renderUI(<BotFiles bot={botNamed("Chief")} />);
    expect(screen.getByText("No files yet. Upload one, or ask Chief to save something.")).toBeInTheDocument();
  });

  it("uploads files into the bot's folder", async () => {
    const { user } = renderUI(<BotFiles bot={botNamed("Chief")} />);
    await user.upload(screen.getByLabelText("Upload files to Chief"), [
      new File(["q3"], "plan.md", { type: "text/markdown" }),
      new File(["a,b"], "leads.csv", { type: "text/csv" }),
    ]);
    const list = await screen.findByRole("list", { name: "Chief's files" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByTitle("plan.md")).toBeInTheDocument();
  });

  it("asks before deleting a file, then removes it", async () => {
    const { user } = renderUI(<BotFiles bot={botNamed("Inbox Manager")} />);
    await user.click(screen.getByRole("button", { name: "Delete reports/inbox-this-week.md" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Delete reports/inbox-this-week.md?");
    expect(dialog).toHaveTextContent("It's removed from Inbox Manager's folder and from your storage.");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(screen.queryByTitle("reports/inbox-this-week.md")).not.toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});

describe("BotFiles on the API", () => {
  const api = withFakeApi();

  it("opens each file from the API in a new tab", async () => {
    api.routes["GET /api/v1/orgs/o1/files?botId=b1"] = {
      status: 200,
      body: [{
        id: "f1", botId: "b1", path: "reports/march.csv", folder: "botdesk/scout", contentType: "text/csv", sizeBytes: 18_204,
        available: true, createdAt: "2026-11-23T08:00:00", updatedAt: "2026-11-23T08:00:00",
      }],
    };
    await signInOnApi();
    renderUI(<BotFiles bot={botNamed("Scout")} />);
    const link = await screen.findByRole("link", { name: "reports/march.csv" });
    expect(link).toHaveAttribute("href", "http://api.test/api/v1/orgs/o1/files/f1/content");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByText(/18 KB/)).toBeInTheDocument();
  });
});
