import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { AppsScreen } from "./apps-screen";

describe("Connect apps in the demo", () => {
  it("shows the demo's connections and lets you connect Gmail", () => {
    renderUI(<AppsScreen />);
    expect(screen.getByRole("heading", { name: "Connected" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Gmail" })).toBeEnabled();
    expect(screen.queryByRole("heading", { name: "Built in" })).not.toBeInTheDocument();
  });
});

describe("Connect apps on the API", () => {
  const api = withFakeApi();
  const demo = {
    id: "demo", name: "Demo", version: "0.1.0", description: "Tools to try approvals with.",
    tools: [
      { name: "demo.send_email", title: "Send email", description: "Sends an email.", risk: "external-send" },
      { name: "demo.read_notes", title: "Read notes", description: "Reads notes.", risk: "read" },
    ],
  };

  it("lists the server's plugins as built in, with each tool's risk", async () => {
    api.routes["GET /api/v1/orgs/o1/plugins"] = { status: 200, body: [demo] };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    const builtIn = await screen.findByRole("region", { name: "Built in" });
    expect(within(builtIn).getByText("Demo")).toBeInTheDocument();
    await user.click(within(builtIn).getByRole("button", { name: /What bots can do \(2\)/ }));
    expect(within(builtIn).getByText("Send email")).toBeInTheDocument();
    expect(within(builtIn).getByText("Sends outside your org")).toBeInTheDocument();
  });

  it("shows the app catalogue as coming soon, with Connect off and nothing pretending to be connected", async () => {
    api.routes["GET /api/v1/orgs/o1/plugins"] = { status: 200, body: [demo] };
    await signInOnApi();
    renderUI(<AppsScreen />);

    expect(screen.getByRole("button", { name: "Connect Gmail" })).toBeDisabled();
    expect(within(screen.getByRole("region", { name: "Coming soon" })).getByText("Gmail")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Connected" })).not.toBeInTheDocument();
    expect(screen.queryByText("Connected", { selector: "span" })).not.toBeInTheDocument();
  });

  it("says so, with Try again, when the plugins can't be loaded", async () => {
    api.routes["GET /api/v1/orgs/o1/plugins"] = { status: 500, body: { detail: "Oops" } };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    expect(await screen.findByText("Couldn't load the built-in apps.")).toBeInTheDocument();
    api.routes["GET /api/v1/orgs/o1/plugins"] = { status: 200, body: [demo] };
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Demo")).toBeInTheDocument();
  });
});
