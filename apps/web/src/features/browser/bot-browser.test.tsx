import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { BotBrowser } from "./bot-browser";

const botNamed = (name: string) => getStoreSnapshot().bots.find((b) => b.name === name)!;
const base = "/api/v1/orgs/o1/bots/b1/browser";
const closed = { available: true, open: false, url: null, title: null, width: 1280, height: 800 };
const open = { ...closed, open: true, url: "https://example.com/login", title: "Sign in · Example" };

describe("BotBrowser in the demo", () => {
  it("says there's no browser to show", async () => {
    renderUI(<BotBrowser bot={botNamed("Chief")} />);
    expect(await screen.findByText("Not available in the demo.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Forget sign-ins" })).not.toBeInTheDocument();
  });
});

describe("BotBrowser on the API", () => {
  const api = withFakeApi();
  const sentInputs = () => api.sent.filter((s) => s.key === `POST ${base}/input`).map((s) => s.body);

  async function show(state: unknown) {
    api.routes[`GET ${base}`] = { status: 200, body: state };
    await signInOnApi();
    return renderUI(<BotBrowser bot={botNamed("Scout")} />);
  }

  it("says so when this server can't show the browser", async () => {
    await show({ ...closed, available: false });
    expect(await screen.findByText("Watching the browser isn't available on this server.")).toBeInTheDocument();
  });

  it("closed: opens a typed address, then shows the page live", async () => {
    api.routes[`POST ${base}/input`] = { status: 200, body: open };
    const { user } = await show(closed);
    expect(await screen.findByText(/Bots never type passwords\./)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Open a page"), "example.com/login");
    await user.click(screen.getByRole("button", { name: "Open" }));

    expect(sentInputs()).toEqual([{ kind: "open", url: "https://example.com/login" }]);
    expect(await screen.findByText("Sign in · Example")).toBeInTheDocument();
    const picture = await screen.findByRole("img", { name: /What Scout's browser shows/ });
    expect(picture.getAttribute("src")).toMatch(/^http:\/\/api\.test\/api\/v1\/orgs\/o1\/bots\/b1\/browser\/screen\?frame=\d+$/);
  });

  it("shows the API's reason when a page can't be opened", async () => {
    api.routes[`POST ${base}/input`] = { status: 400, body: { detail: "That address is on a private network." } };
    const { user } = await show(closed);
    await user.type(await screen.findByLabelText("Open a page"), "10.0.0.1");
    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That address is on a private network.");
  });

  it("open: watch only until Take over, then clicks and keys go to the page", async () => {
    api.routes[`POST ${base}/input`] = { status: 200, body: open };
    const { user } = await show(open);
    await screen.findByRole("img", { name: /What Scout's browser shows/ });
    expect(screen.queryByRole("application")).not.toBeInTheDocument();

    await user.click(screen.getByRole("switch", { name: "Take over" }));
    const frame = screen.getByRole("application", { name: "Scout's browser, taking over" });
    expect(frame).toHaveFocus();

    // The picture is shown at half size, 100px in: a click in its middle is the page's middle.
    const picture = within(frame).getByRole("img");
    vi.spyOn(picture, "getBoundingClientRect").mockReturnValue(DOMRect.fromRect({ x: 100, y: 20, width: 640, height: 400 }));
    fireEvent.click(frame, { clientX: 420, clientY: 220 });
    await user.keyboard("hi{Shift>}{Tab}{/Shift}");

    await vi.waitFor(() => expect(sentInputs()).toEqual([
      { kind: "click", x: 640, y: 400 },
      { kind: "type", text: "hi" },
      { kind: "key", key: "Shift+Tab" },
    ]));
  });

  it("asks before forgetting sign-ins, then forgets them", async () => {
    api.routes[`DELETE ${base}`] = { status: 204 };
    const { user } = await show(open);
    await user.click(await screen.findByRole("button", { name: "Forget sign-ins" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Every site Scout is signed in to will ask it to sign in again.");
    await user.click(within(dialog).getByRole("button", { name: "Forget sign-ins" }));

    await vi.waitFor(() => expect(api.sent.some((s) => s.key === `DELETE ${base}`)).toBe(true));
    expect(await screen.findByLabelText("Open a page")).toBeInTheDocument();
  });
});
