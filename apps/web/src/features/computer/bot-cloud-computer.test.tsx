import { act, fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { BotCloudComputer } from "./bot-cloud-computer";

const base = "/api/v1/orgs/o1/bots/b1/computer";
const none = {
  status: "none", name: null, remoteId: null, cpu: null, ram: null, region: null, startedAt: null, lastUsedAt: null,
  idleStopsAt: null, error: null, orgoUrl: null, apps: [], previews: [],
};
const running = {
  ...none, status: "running", name: "botdesk-scout", remoteId: "c1", cpu: 2, ram: 8, region: "us-east",
  startedAt: "2026-11-27T09:00:00Z", idleStopsAt: "2026-11-27T09:40:00Z", orgoUrl: "https://www.orgo.ai/computers/c1",
  apps: [{ name: "web", port: 3000, status: "running" }],
  previews: [{ url: "https://web-ab3k.orgo.dev", port: 3000, access: "team" }],
};
const stopped = { ...running, status: "stopped", apps: [], previews: [] };
const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);

const scout = () => ({ ...getStoreSnapshot().bots.find((b) => b.id === "b1")!, computer: "cloud" as const });

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("BotCloudComputer on the API", () => {
  const api = withFakeApi();
  const screens = () => api.sent.filter((s) => s.key === `GET ${base}/screen`).length;
  const inputs = () => api.sent.filter((s) => s.key === `POST ${base}/input`).map((s) => s.body);
  let frames = 0;

  beforeEach(() => {
    frames = 0;
    // jsdom has no blob: URLs; each picture gets a name of its own.
    Object.assign(URL, { createObjectURL: vi.fn(() => `blob:frame-${++frames}`), revokeObjectURL: vi.fn() });
    setVisibility("visible");
  });

  async function show(state: unknown) {
    api.routes[`GET ${base}`] = { status: 200, body: state };
    api.routes[`GET ${base}/screen`] = { status: 200, body: jpeg };
    api.routes[`POST ${base}/input`] = { status: 204 };
    await signInOnApi();
    return renderUI(<BotCloudComputer bot={scout()} />);
  }

  it("starts, stops and (after asking) deletes the computer", async () => {
    api.routes[`POST ${base}/start`] = { status: 200, body: running };
    api.routes[`POST ${base}/stop`] = { status: 200, body: stopped };
    api.routes[`DELETE ${base}`] = { status: 204 };
    const { user } = await show(none);
    expect(await screen.findByText("No computer yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete computer" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Start" }));
    expect(await screen.findByText("Running")).toBeInTheDocument();
    expect(screen.getByText("2 vCPU · 8 GB · us-east")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Orgo" })).toHaveAttribute("href", "https://www.orgo.ai/computers/c1");
    expect(screen.getByText("web")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://web-ab3k.orgo.dev" })).toHaveAttribute("target", "_blank");
    expect(screen.getByText(/only people in your Orgo workspace can open it/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(await screen.findByText("Its disk is kept: Start picks up where it left off.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete computer" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Everything on its disk is lost");
    await user.click(within(dialog).getByRole("button", { name: "Delete computer" }));
    expect(await screen.findByText("No computer yet")).toBeInTheDocument();
    expect(api.sent.map((s) => s.key)).toEqual(expect.arrayContaining([`POST ${base}/start`, `POST ${base}/stop`, `DELETE ${base}`]));
  });

  it("shows the API's reason when the computer can't start", async () => {
    api.routes[`POST ${base}/start`] = { status: 402, body: { detail: "Orgo says the account is out of credit." } };
    const { user } = await show(none);
    await user.click(await screen.findByRole("button", { name: "Start" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Orgo says the account is out of credit.");
  });

  it("asks for the screen about once a second, one picture at a time, and never while the page is hidden", async () => {
    await show(running);
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    await vi.waitFor(() => expect(screen.getByRole("img", { name: "Scout's computer screen" })).toHaveAttribute("src", "blob:frame-1"));
    expect(screens()).toBe(1);

    await act(() => vi.advanceTimersByTimeAsync(1000));
    await vi.waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "blob:frame-2"));
    expect(screens()).toBe(2);
    // The picture before is freed once the new one is shown.
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:frame-1");

    setVisibility("hidden");
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(screens()).toBe(2);

    setVisibility("visible");
    await vi.waitFor(() => expect(screens()).toBe(3));
  });

  it("a screen the API can't give (the computer stopped) shows the computer as it is now", async () => {
    let answer = () => {};
    api.routes[`GET ${base}`] = { status: 200, body: running };
    api.routes[`GET ${base}/screen`] = { status: 409, body: { detail: "The computer isn't running." }, wait: new Promise<void>((resolve) => { answer = resolve; }) };
    await signInOnApi();
    renderUI(<BotCloudComputer bot={scout()} />);
    expect(await screen.findByText("Running")).toBeInTheDocument();

    // It stopped on its own (idle) while the picture was on its way.
    api.routes[`GET ${base}`] = { status: 200, body: stopped };
    answer();
    expect(await screen.findByText("Stopped", { selector: "p" })).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "Take over" })).not.toBeInTheDocument();
  });

  it("a screen that keeps failing is asked for less often, and one that can't be had isn't asked for again", async () => {
    await show(running);
    api.routes[`GET ${base}/screen`] = { status: 500, body: { detail: "Orgo didn't answer." } };
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    await vi.waitFor(() => expect(screens()).toBe(1));
    await act(() => vi.advanceTimersByTimeAsync(3000));
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(screens()).toBe(3);
    // Three in a row: the next try waits 30 s.
    await act(() => vi.advanceTimersByTimeAsync(20_000));
    expect(screens()).toBe(3);
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(screens()).toBe(4);

    api.routes[`GET ${base}/screen`] = { status: 404, body: { detail: "That bot has no computer." } };
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(screens()).toBe(5);
    expect(screen.getByText("That bot has no computer. Reopen the Computer tab to try again.")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(120_000));
    expect(screens()).toBe(5);
  });

  it("a 409 asks for the computer's state once, not on every retry", async () => {
    await show(running);
    api.routes[`GET ${base}/screen`] = { status: 409, body: { detail: "The computer isn't running." } };
    const states = () => api.sent.filter((s) => s.key === `GET ${base}`).length;
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    await vi.waitFor(() => expect(screens()).toBe(1));
    await vi.waitFor(() => expect(states()).toBe(2)); // the tab's first check, and the 409's
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(screens()).toBe(2);
    expect(states()).toBe(2);
  });

  it("checks the computer one request at a time, and an older answer never replaces a newer one", async () => {
    let answer = () => {};
    api.routes[`GET ${base}`] = { status: 200, body: { ...running, status: "starting" }, wait: new Promise<void>((resolve) => { answer = resolve; }) };
    api.routes[`GET ${base}/screen`] = { status: 200, body: jpeg };
    await signInOnApi();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    renderUI(<BotCloudComputer bot={scout()} />);
    const states = () => api.sent.filter((s) => s.key === `GET ${base}`).length;
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(states()).toBe(1); // still waiting for the first answer

    // A newer check (the tab coming back into view) says it's running; then the old "starting" lands.
    api.routes[`GET ${base}`] = { status: 200, body: running };
    await act(() => actions.loadComputer("b1"));
    expect(screen.getByText("Running")).toBeInTheDocument();
    answer();
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.queryByText("Starting…")).not.toBeInTheDocument();
  });

  it("asks for no screen while the computer isn't running", async () => {
    await show(stopped);
    expect(await screen.findByText("Stopped", { selector: "p" })).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(screens()).toBe(0);
    expect(screen.queryByRole("switch", { name: "Take over" })).not.toBeInTheDocument();
  });

  /** Taking over a 1920×1200 screen shown at a quarter of its width, 100px in. */
  async function takeOver() {
    const rendered = await show(running);
    await screen.findByRole("img", { name: "Scout's computer screen" });
    await rendered.user.click(screen.getByRole("switch", { name: "Take over" }));
    const frame = screen.getByRole("application", { name: "Scout's computer, taking over" });
    const picture = within(frame).getByRole("img");
    Object.defineProperties(picture, { naturalWidth: { value: 1920 }, naturalHeight: { value: 1200 } });
    vi.spyOn(picture, "getBoundingClientRect").mockReturnValue(DOMRect.fromRect({ x: 100, y: 20, width: 480, height: 300 }));
    return { ...rendered, frame, picture };
  }
  const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  it("taking over: clicks land at the screen's own pixels, a double click and a right click too", async () => {
    const { frame, picture } = await takeOver();
    expect(frame).toHaveFocus();

    fireEvent.click(picture, { clientX: 340, clientY: 170 });
    await vi.waitFor(() => expect(inputs()).toEqual([{ kind: "click", x: 960, y: 600 }]));

    fireEvent.click(picture, { clientX: 100, clientY: 20 });
    fireEvent.click(picture, { clientX: 101, clientY: 21 });
    fireEvent.contextMenu(picture, { clientX: 580, clientY: 320 });
    await vi.waitFor(() => expect(inputs()).toEqual([
      { kind: "click", x: 960, y: 600 },
      { kind: "double_click", x: 0, y: 0 },
      { kind: "right_click", x: 1919, y: 1199 },
    ]));
  });

  it("taking over: a slow double click is still one, a third click starts afresh, and a click elsewhere is its own", async () => {
    const { picture } = await takeOver();
    fireEvent.click(picture, { clientX: 340, clientY: 170 });
    await wait(300);
    fireEvent.click(picture, { clientX: 340, clientY: 170 });
    fireEvent.click(picture, { clientX: 340, clientY: 170 });
    await vi.waitFor(() => expect(inputs()).toEqual([{ kind: "double_click", x: 960, y: 600 }, { kind: "click", x: 960, y: 600 }]));

    fireEvent.click(picture, { clientX: 100, clientY: 20 });
    fireEvent.click(picture, { clientX: 340, clientY: 170 });
    await vi.waitFor(() => expect(inputs().slice(2)).toEqual([{ kind: "click", x: 0, y: 0 }, { kind: "click", x: 960, y: 600 }]));
  });

  it("taking over: a click goes before typing, a key or a scroll that came after it", async () => {
    const { user, picture, frame } = await takeOver();
    fireEvent.click(picture, { clientX: 340, clientY: 170 });
    await user.keyboard("hi");
    fireEvent.click(picture, { clientX: 100, clientY: 20 });
    await user.keyboard("{Enter}");
    fireEvent.click(picture, { clientX: 340, clientY: 170 });
    fireEvent.wheel(frame, { deltaY: -120, clientX: 340, clientY: 170 });
    await vi.waitFor(() => expect(inputs()).toEqual([
      { kind: "click", x: 960, y: 600 },
      { kind: "type", text: "hi" },
      { kind: "click", x: 0, y: 0 },
      { kind: "key", key: "Enter" },
      { kind: "click", x: 960, y: 600 },
      { kind: "scroll", direction: "up", x: 960, y: 600 },
    ]));
  });

  it("taking over: turning it off drops a click still waiting, and Ctrl+Shift+C stays with this browser", async () => {
    const { user, picture, frame } = await takeOver();
    frame.focus();
    await user.keyboard("{Control>}{Shift>}C{/Shift}{/Control}");
    fireEvent.click(picture, { clientX: 340, clientY: 170 });
    await user.click(screen.getByRole("switch", { name: "Take over" }));
    await wait(500);
    expect(inputs()).toEqual([]);
  });

  it("taking over: typing goes in batches, shortcuts and key buttons as keys, and the field types its text", async () => {
    const { user } = await show(running);
    await screen.findByRole("img", { name: "Scout's computer screen" });
    await user.click(screen.getByRole("switch", { name: "Take over" }));

    await user.keyboard("ls -la");
    await user.keyboard("{Enter}{Control>}c{/Control}");
    await user.click(screen.getByRole("button", { name: "Press Ctrl+L" }));
    await user.click(screen.getByRole("button", { name: "Press Up arrow" }));
    await user.click(screen.getByLabelText("Type on the computer"));
    await user.paste("git status");
    await user.click(screen.getByRole("button", { name: "Type" }));

    await vi.waitFor(() => expect(inputs()).toEqual([
      { kind: "type", text: "ls -la" },
      { kind: "key", key: "Enter" },
      { kind: "key", key: "ctrl+c" },
      { kind: "key", key: "ctrl+l" },
      { kind: "key", key: "Up" },
      { kind: "type", text: "git status" },
    ]));
    expect(screen.getByLabelText("Type on the computer")).toHaveValue("");
  });

  it("scrolls with the wheel, at the pointer", async () => {
    const { user } = await show(running);
    await screen.findByRole("img", { name: "Scout's computer screen" });
    await user.click(screen.getByRole("switch", { name: "Take over" }));
    const frame = screen.getByRole("application", { name: "Scout's computer, taking over" });
    const picture = within(frame).getByRole("img");
    Object.defineProperties(picture, { naturalWidth: { value: 1920 }, naturalHeight: { value: 1200 } });
    vi.spyOn(picture, "getBoundingClientRect").mockReturnValue(DOMRect.fromRect({ x: 0, y: 0, width: 960, height: 600 }));

    fireEvent.wheel(frame, { deltaY: 120, clientX: 480, clientY: 300 });
    await vi.waitFor(() => expect(inputs()).toEqual([{ kind: "scroll", direction: "down", x: 960, y: 600 }]));
  });
});
