import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { apiDm, signInOnApi, withFakeApi } from "@/test/fake-api";
import { Composer } from "./composer";

const thread = (id: string) => getStoreSnapshot().threads.find((t) => t.id === id)!;
const lastMessage = (threadId: string) => getStoreSnapshot().messages.filter((m) => m.threadId === threadId).at(-1)!;
const picker = () => screen.getByLabelText("Choose files to attach");
const chips = () => screen.getByRole("list", { name: "Attached files" });

const apiFile = (id: string, path: string, botId: string | null) => ({
  id, botId, path, folder: botId ? "botdesk/scout" : "botdesk/_shared", contentType: "text/markdown", sizeBytes: 2048,
  available: true, createdAt: "2026-11-25T08:00:00", updatedAt: "2026-11-25T08:00:00",
});
const sentMessage = (threadId: string, parts: unknown[]) => ({
  id: "m9", threadId, author: { type: "user", id: "u1" }, parts, status: "complete", createdAt: "2026-11-25T08:01:00Z", runIds: [],
});

describe("Composer attachments on the API", () => {
  const api = withFakeApi();
  const upload = "POST /api/v1/orgs/o1/files";
  const sent = (key: string) => api.sent.filter((r) => r.key === key).map((r) => r.body);

  it("uploads a picked file into the DM's bot's chat folder, then sends it with the text", async () => {
    api.routes[upload] = { status: 201, body: apiFile("f1", "chat/plan.md", "b1") };
    api.routes["POST /api/v1/orgs/o1/threads/t1/messages"] = { status: 201, body: sentMessage("t1", []) };
    await signInOnApi();
    const { user } = renderUI(<Composer thread={thread("t1")} />);

    await user.upload(picker(), new File(["# Plan"], "plan.md", { type: "text/markdown" }));

    expect(await within(chips()).findByText("6 B")).toBeInTheDocument(); // uploaded: its size
    expect(within(chips()).getByText("plan.md")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("plan.md attached.");
    expect(sent(upload)[0]).toMatchObject({ botId: "b1", path: "chat/plan.md" });

    await user.type(screen.getByRole("textbox", { name: "Message Scout" }), "Read this{Enter}");
    expect(sent("POST /api/v1/orgs/o1/threads/t1/messages")).toEqual([{ text: "Read this", attachments: ["f1"] }]);
    expect(screen.queryByRole("list", { name: "Attached files" })).not.toBeInTheDocument();
  });

  it("shows why an upload failed, and still sends the text without it", async () => {
    api.routes[upload] = { status: 400, body: { detail: "That file is too big: files can be up to 25 MB." } };
    api.routes["POST /api/v1/orgs/o1/threads/t1/messages"] = { status: 201, body: sentMessage("t1", []) };
    await signInOnApi();
    const { user } = renderUI(<Composer thread={thread("t1")} />);

    await user.upload(picker(), new File(["big"], "video.mp4", { type: "video/mp4" }));

    expect(await within(chips()).findByText("That file is too big: files can be up to 25 MB.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("video.mp4 didn't upload. That file is too big");
    expect(screen.getByRole("button", { name: "Retry video.mp4" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

    await user.type(screen.getByRole("textbox", { name: "Message Scout" }), "Here's the summary instead");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(sent("POST /api/v1/orgs/o1/threads/t1/messages")).toEqual([{ text: "Here's the summary instead" }]);
  });

  it("in a group, uploads to the shared folder (no botId)", async () => {
    const group = {
      ...apiDm, id: "t2", kind: "group", title: "Launch", botId: undefined, leadBotId: "b1",
      participants: [{ type: "user", id: "u1" }, { type: "bot", id: "b1" }],
    };
    api.routes["GET /api/v1/orgs/o1/threads"] = { status: 200, body: [apiDm, group] };
    api.routes[upload] = { status: 201, body: apiFile("f2", "chat/brief.md", null) };
    await signInOnApi();
    const { user } = renderUI(<Composer thread={thread("t2")} />);

    await user.upload(picker(), new File(["brief"], "brief.md", { type: "text/markdown" }));

    await within(chips()).findByText("5 B");
    expect(sent(upload)).toHaveLength(1);
    expect(sent(upload)[0]).toMatchObject({ path: "chat/brief.md" });
    expect(sent(upload)[0]).not.toHaveProperty("botId");
  });
});

describe("Composer attachments in the demo", () => {
  it("dropping a file attaches it, and Send sends it alone", async () => {
    const { user } = renderUI(<Composer thread={thread("t_chief")} />);
    const box = screen.getByRole("textbox", { name: "Message Chief" });
    const file = new File(["a,b"], "leads.csv", { type: "text/csv" });

    fireEvent.drop(box, { dataTransfer: { files: [file], types: ["Files"] } });

    expect(await within(chips()).findByText("3 B")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(lastMessage("t_chief").parts).toEqual([
      { type: "file", fileId: expect.any(String), botId: "b_chief", path: "chat/leads.csv", contentType: "text/csv", sizeBytes: 3 },
    ]);
  });

  it("a pasted screenshot gets the time it was pasted, so a second one doesn't replace it", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date(2026, 10, 25, 10, 30, 5) });
    renderUI(<Composer thread={thread("t_chief")} />);
    const box = screen.getByRole("textbox", { name: "Message Chief" });
    const shot = () => new File(["png"], "image.png", { type: "image/png" });

    fireEvent.paste(box, { clipboardData: { files: [shot()], types: ["Files"] } });
    fireEvent.paste(box, { clipboardData: { files: [shot()], types: ["Files"] } });

    expect(await within(chips()).findByText("image-2026-11-25-103005.png")).toBeInTheDocument();
    expect(within(chips()).getByText("image-2026-11-25-103005 (2).png")).toBeInTheDocument();
  });

  it("Remove takes a file off the message and puts the keyboard back in the box", async () => {
    const { user } = renderUI(<Composer thread={thread("t_chief")} />);
    await user.upload(picker(), new File(["x"], "notes.txt", { type: "text/plain" }));
    await user.click(await screen.findByRole("button", { name: "Remove notes.txt" }));
    expect(screen.queryByRole("list", { name: "Attached files" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message Chief" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});
